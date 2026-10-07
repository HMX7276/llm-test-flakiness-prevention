"""Join the first human return to frozen evidence; never adjudicate on their behalf."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.import_human_review import validate
from runner.prepare import save
from runner.rule_review_status import status as rule_status

SOURCE_SHA = 'e3aa643e2dfcc300f7923721ec9fdd062609ad3ccd9bf2f6b31bebb00528ae26'
FIELDS = ('correctness', 'robustness', 'adequacy')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    v2_path = ROOT / 'analysis/human_semantic_v2_reconciliation.json'
    v2_review = read(v2_path) if v2_path.exists() else {}
    base = ROOT / 'review/semantic_v1'
    raw_path = base / 'returned' / (SOURCE_SHA + '.json')
    raw = raw_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA
    payload = json.loads(raw.decode('utf-8-sig'))
    mapping = read(base / 'mapping_private.json')
    accepted = read(base / 'accepted' / (SOURCE_SHA + '.json'))
    checked = validate(payload, mapping)
    assert checked['completed'] == accepted['completed']
    ai = {r['review_id']: r for r in read(base / 'ai_assessment_separate.json')}
    human = {r['review_id']: r for r in payload['items']}
    issues = {
        'R003': {
            'field': 'correctness', 'proposed': 'incorrect',
            'reason': '原代码先创建 topic 再替换时钟，首个 idle_time == 0.0 不成立；原执行 30/30 fail。人工理由也指出会失败，但标签为 correct。评价应针对未修改原代码。'},
        'R025': {
            'field': 'correctness', 'proposed': 'incorrect',
            'reason': 'from lithoxyl import MomentAccumulator 在固定版本发生 ImportError，收集失败。应从 lithoxyl.moment 导入；正文断言合理不代表原测试可正确执行。'},
        'R039': {
            'field': 'correctness', 'proposed': 'incorrect',
            'reason': 'from lithoxyl import MomentAccumulator 在固定版本发生 ImportError，收集失败；同 R025。'},
        'R052': {
            'field': 'correctness', 'proposed': 'incorrect',
            'reason': 'from lithoxyl import MomentAccumulator 在固定版本发生 ImportError，收集失败；同 R025。'},
        'R060': {
            'field': 'robustness', 'proposed': 'fragile',
            'reason': '人工理由指出两次真实时钟读取差异，但标签为 robust。原主协议 30/30 pass；独立读取间隙扰动为 14 pass/16 fail，确认时钟依赖。仅改 pytest.approx 不能保证抵抗更长合法延迟。'}
    }
    scope_ids = {'R013', 'R016', 'R024', 'R034', 'R042', 'R050', 'R054'}
    rows = []
    for item in mapping:
        rid = item['review_id']
        source = ROOT / item['code_path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item['code_sha256'], rid
        # The packet displays universal-newline text; the frozen hash binds file bytes.
        assert source.read_text(encoding='utf-8') == item['code'], rid
        evaluation_path = source.parent / 'evaluation/summary.json'
        outcome = read(evaluation_path)
        row = {
            'review_id': rid, 'run': item['private_run'], 'output': item['private_output'],
            'target': item['target'], 'code_path': item['code_path'], 'code_sha256': item['code_sha256'],
            'human_raw': human[rid], 'assistant_frozen': ai[rid],
            'execution': {k: outcome.get(k) for k in ('status', 'counts', 'executions')},
            'execution_evidence': str(evaluation_path.relative_to(ROOT)),
            'adjudication_status': 'pending_human_confirmation' if rid in issues else 'no_label_change_proposed',
            'assistant_proposal': issues.get(rid),
            'scope_note': '人工指出共享 topic 注册表的套件组合/重跑风险；保留 fragile。原主协议为独立进程，30/30 pass 不反驳此风险。' if rid in scope_ids else None,
        }
        if rid == 'R060':
            followup = ROOT / 'runs/semantic_followup_v2/d032_clock_read_gap/summary.json'
            posthoc = read(followup)
            assert posthoc['code_sha256'] == item['code_sha256']
            row['posthoc_evidence'] = str(followup.relative_to(ROOT))
            row['posthoc_counts'] = posthoc['counts']
        rows.append(row)
    reason_notes = [
        {'review_id': 'R021', 'status': 'assistant_correction_to_reason_only',
         'note': 'incorrect 标签有依据。理由中关于 statistics.skew 的解释不准确：当前 Python 标准库 statistics 没有 skew 或 kurtosis；补上 import statistics 后仍会 AttributeError，不是该标准库函数返回了校正偏度。原始理由保留。'},
        {'review_id': 'R011', 'status': 'additional_evidence',
         'note': 'incorrect 标签有依据，人工发现了错误高阶矩期望；原代码还存在 lithoxyl 根模块导入错误，原执行在收集阶段失败。不能把数学分析写成已执行到高阶矩断言。'},
        {'review_id': 'R042', 'status': 'text_appears_truncated',
         'note': '理由结束于“首个断言”，可能未写完；已有明确的注册表依赖解释及三个标签，仍按完整提交计数，不推断缺失句子。'},
        {'review_id': 'R047', 'status': 'human_interpretation_retained',
         'note': '人工认为直接设置 last_event 后的真实 send 断言仍有意义。保留 meaningful，记录未覆盖构造与 sync，不能据此宣称覆盖完整。'}
    ]
    counts = {f: dict(Counter(r[f] for r in checked['completed'])) for f in FIELDS}
    adjudication_path = base / 'adjudications/2026-10-05_confirmed_five.json'
    confirmed_ids = set()
    for row in rows:
        row['human_effective_labels'] = {f: row['human_raw'][f] for f in FIELDS}
    if adjudication_path.exists():
        adjudication = read(adjudication_path)
        assert adjudication['schema'] == 'human-semantic-adjudication-v1'
        assert adjudication['source_sha256'] == SOURCE_SHA
        assert adjudication['reviewer'] == payload['reviewer']
        assert adjudication['reviewer_type'] == 'human'
        indexed = {row['review_id']: row for row in rows}
        for change in adjudication['changes']:
            rid = change['review_id']
            assert rid in issues and rid not in confirmed_ids
            row = indexed[rid]
            field = change['field']
            assert change['code_sha256'] == row['code_sha256']
            assert field == issues[rid]['field']
            assert change['old_value'] == row['human_raw'][field]
            assert change['new_value'] == issues[rid]['proposed']
            row['human_effective_labels'][field] = change['new_value']
            row['adjudication_status'] = 'confirmed_by_human_after_discussion'
            row['adjudication_evidence'] = str(adjudication_path.relative_to(ROOT))
            confirmed_ids.add(rid)
    pending_ids = sorted(set(issues) - confirmed_ids)
    effective_counts = {f: dict(Counter(r['human_effective_labels'][f] for r in rows)) for f in FIELDS}
    by_run = {}
    for run in sorted({r['run'] for r in rows}):
        subset = [r['human_raw'] for r in rows if r['run'] == run]
        effective = [r['human_effective_labels'] for r in rows if r['run'] == run]
        by_run[run] = {'received': len(subset), **{f: dict(Counter(r[f] for r in subset)) for f in FIELDS},
                       'effective_label_counts': {f: dict(Counter(r[f] for r in effective)) for f in FIELDS}}
    result = {
        'schema': 'human-semantic-reconciliation-v1', 'source_sha256': SOURCE_SHA,
        'source_archive': str(raw_path.relative_to(ROOT)), 'reviewer': payload['reviewer'],
        'exported_at': payload.get('exported_at'), 'imported_utc': accepted['imported_utc'],
        'complete_received': len(checked['completed']), 'partial': len(checked['partial']),
        'not_returned': checked['not_returned'], 'verified_code_hashes': len(rows),
        'raw_label_counts': counts, 'by_run': by_run,
        'effective_label_counts': effective_counts,
        'pending_label_confirmation': pending_ids, 'proposed_changes_applied': bool(confirmed_ids),
        'confirmed_changes': sorted(confirmed_ids), 'raw_labels_unchanged': True,
        'adjudication_status': 'resolved' if not pending_ids else 'pending_human_confirmation',
        'adjudication_evidence': str(adjudication_path.relative_to(ROOT)) if confirmed_ids else None,
        'scope_review_ids': sorted(scope_ids), 'reason_notes': reason_notes,
        'rules_v2_human_review_status': rule_status(),
        'development_v2_generated_tests_human_review_status': {'scope':'separate_packet',
            'completed_received':v2_review.get('complete_received',0),
            'adjudication_status':v2_review.get('adjudication_status','awaiting_user_export')},
        'agreement_coefficient': None,
        'limitations': ['One human reviewer; assistant is not a second human.',
                        'These are development labels, not a formal held-out evaluation.',
                        'Submitted labels and confirmed adjudications are distinct.',
                        'No recalculation or pooling of frozen experimental outcomes.'],
        'rows': rows,
    }
    save(ROOT / 'analysis/human_semantic_reconciliation.json', result)
    lines = [
        '人工语义核验回收与分歧记录', '',
        f"复核者：{payload['reviewer']}；提交时间：{payload.get('exported_at')}。",
        f'原文件 SHA-256：{SOURCE_SHA}',
        '已接收完整标签 60/60；部分填写 0；缺项 0；60 项原代码及冻结映射哈希均匹配。',
        f'本人已明确确认 {len(confirmed_ids)} 项调整，剩余 {len(pending_ids)} 项待确认。首次独立标注保留；讨论后确认标签单独存储。', '',
        '首次独立标签汇总：',
        '正确性：47 correct，13 incorrect；稳健性：45 robust，15 fragile；充分性：50 meaningful，10 weak_or_masked。',
        '其中 48 项为 development_v1 主生成，12 项为独立导入路径诊断。两类数据不能当作同一主试验合并估计效果。', '',
        '讨论后有效标签汇总：' + json.dumps(effective_counts, ensure_ascii=False), '',
        '5 项标签调整记录：',
    ]
    for rid, issue in issues.items():
        state = '本人已确认' if rid in confirmed_ids else '待本人确认'
        lines.append(f"{rid}（{state}）：{issue['field']} {human[rid][issue['field']]} → {issue['proposed']}。{issue['reason']}")
    lines.extend(['', '理由说明与范围问题：'])
    for note in reason_notes:
        lines.append(note['review_id'] + '：' + note['note'])
    lines.extend([
        '注册表依赖：' + '、'.join(sorted(scope_ids)) + ' 的 fragile 标签保留；这些指出套件组合/重跑风险，与独立进程通过并不矛盾。',
        '同一测试中，错误断言可以是确定性失败；correctness、robustness、adequacy 不互相替代。', '',
        f"后续范围：v2 独立核验包已收到 {v2_review.get('complete_received',0)}/36 项。规则意图单独记录，已收到 {len(rule_status()['completed'])}/3 项；不从测试标签推断规则判断。",
        '只有一位人类复核者；不报告双人人工一致性或 kappa。AI 冻结判断与原始人工判断逐项并列保存在同名 JSON。', '',
        '证据索引（使用讨论后有效标签；原始理由与标签仍保留在 JSON human_raw 中）：',
    ])
    for row in rows:
        h = row['human_effective_labels']
        lines.append(f"{row['review_id']} | {row['run']}/{row['output']} | "
                     + '/'.join(h[f] for f in FIELDS) + f" | {row['execution']['status']} | {row['code_path']}")
    (ROOT / 'analysis/human_semantic_reconciliation.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('complete_received', 'verified_code_hashes', 'raw_label_counts', 'pending_label_confirmation')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
