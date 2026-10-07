"""Preserve raw labels and apply only separately archived explicit human decisions."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.lean_followup_v1 import RUN, verified, load
from runner.prepare import save

SHA = '41cbe15e3d46c41885c6e0ba03c4600240ddf2f6ea84dc7819e878b3f5e4fd70'
FIELDS = ['correctness', 'robustness', 'adequacy']
NOTES = {
    'L005': 'Missing import random; original execution fails with NameError in 30/30 runs. Correctness conflicts with execution.',
    'L039': 'Missing import random; original execution fails with NameError in 30/30 runs. Correctness conflicts with execution.',
    'L014': 'Correctness was absent in the original export; the explicit human completion is archived separately.',
    'L012': 'In the fixed seed-42 example, actual BRPOIG8 differs from asserted 71R1O51; failure is not only hypothetical across seeds.',
    'L033': 'In the fixed seed-42 example, actual BRPOIG8 differs from asserted N9K7X2Q.',
    'L022': 'Missing tale fixture causes a setup-stage error, not a collection error.',
    'L030': 'Bound self argument causes TypeError in the clock lambda before the later clock-oracle issue.',
    'L032': 'The random.sample stub ignores population and k, masking length behavior. Zero of two diagnostic defects detected; this alone does not invalidate every assertion.',
    'L041': 'After send, the supplied clock sequence produces idle_time 0, while the assertion expects 5.'}


def counts(rows):
    return {f: {'available': sum(bool(r.get(f)) for r in rows),
                'counts': dict(Counter(r[f] for r in rows if r.get(f)))} for f in FIELDS}


def main():
    frozen = verified()
    packet = ROOT / 'review/semantic_lean_v1'
    raw_path = packet / 'returned' / (SHA + '.json')
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == SHA
    raw = load(raw_path)
    accepted = load(packet / 'accepted' / (SHA + '.json'))
    assert accepted['source_sha256'] == SHA
    labels = {r['review_id']: r for r in raw['items']}
    assert len(labels) == len(raw['items']) == 48
    imported = {r['review_id']: r for r in accepted['completed'] + accepted['partial']}
    assert labels == imported
    effective = {rid: dict(label) for rid, label in labels.items()}
    applied = []
    for path in sorted((packet / 'adjudications').glob('*.json')):
        ledger = load(path)
        assert ledger['source_sha256'] == SHA and ledger['actor_type'] == 'human'
        for decision in ledger['decisions']:
            rid, field = decision['review_id'], decision['field']
            assert labels[rid]['code_sha256'] == decision['code_sha256']
            assert effective[rid][field] == decision['original']
            effective[rid][field] = decision['adjudicated']
            for other, value in ledger['unchanged_fields'].items():
                assert effective[rid][other] == value
            applied.append({**decision, 'ledger': path.relative_to(ROOT).as_posix(),
                            'ledger_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'actor': ledger['actor'], 'unchanged_fields_reason': ledger['unchanged_fields_reason']})
    completions = []
    for path in sorted((packet / 'completions').glob('*.json')):
        decision = load(path)
        assert decision['source_sha256'] == SHA and decision['actor_type'] == 'human'
        rid, field = decision['review_id'], decision['field']
        assert labels[rid]['code_sha256'] == decision['code_sha256']
        assert field in FIELDS and decision['original'] is None and not effective[rid].get(field)
        effective[rid][field] = decision['completed']
        for other, value in decision['unchanged_fields'].items():
            assert effective[rid][other] == value
        completions.append({**decision, 'ledger': path.relative_to(ROOT).as_posix(),
                            'ledger_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    mapping = load(packet / 'mapping_private.json')
    assert set(labels) == {r['review_id'] for r in mapping}
    cells = {c['output_id']: c for c in frozen['cells']}
    rows = []
    for m in mapping:
        rid, oid = m['review_id'], m['private_output']
        source = ROOT / m['code_path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == labels[rid]['code_sha256'] == m['code_sha256']
        assert source.read_text(encoding='utf-8') == m['code']
        cell = cells[oid]
        primary = load(RUN / 'outputs' / oid / 'evaluation/summary.json')
        quality_path = RUN / 'quality' / oid / 'summary.json'
        quality = load(quality_path) if quality_path.exists() else None
        supplemental_path = RUN / 'reviewed_execution' / oid / 'summary.json'
        supplemental = load(supplemental_path) if supplemental_path.exists() else None
        supplemental_quality_path = RUN / 'reviewed_quality' / oid / 'summary.json'
        supplemental_quality = load(supplemental_quality_path) if supplemental_quality_path.exists() else None
        missing = [f for f in FIELDS if not effective[rid].get(f)]
        raw_conflict = labels[rid].get('correctness') == 'correct' and primary['status'] == 'persistent_failure'
        conflict = effective[rid].get('correctness') == 'correct' and primary['status'] == 'persistent_failure'
        adjudicated = any(d['review_id'] == rid for d in applied)
        completed_by_human = any(d['review_id'] == rid for d in completions)
        rows.append({'review_id': rid, 'output_id': oid, 'code_sha256': m['code_sha256'],
                     **{k: cell[k] for k in ['model_id', 'method', 'task_id']},
                     'raw_labels': labels[rid], 'effective_labels': effective[rid], 'missing_fields': missing,
                     'primary_outcome': primary['status'], 'primary_counts': primary['counts'],
                     'diagnostic_stable_detected': quality['stable_detected'] if quality else None,
                     'diagnostic_defects': quality['total'] if quality else None,
                     'supplemental_execution': supplemental,
                     'supplemental_diagnostic_quality': supplemental_quality,
                     'raw_execution_conflict': raw_conflict, 'execution_conflict': conflict,
                     'adjudication_status': ('awaiting_human_reply' if conflict or missing else
                                             'human_adjudicated' if adjudicated else
                                             'human_completed' if completed_by_human else 'no_change_requested'),
                     'assistant_evidence_note': NOTES.get(rid)})
    raw_complete = [r['raw_labels'] for r in rows if all(r['raw_labels'].get(f) for f in FIELDS) and r['raw_labels'].get('reason', '').strip()]
    complete = [r['effective_labels'] for r in rows if not r['missing_fields'] and r['effective_labels'].get('reason', '').strip()]
    groups = []
    for model, method in sorted({(r['model_id'], r['method']) for r in rows}):
        members = [r for r in rows if (r['model_id'], r['method']) == (model, method)]
        groups.append({'model': model, 'method': method, 'reviewed_sample': len(members),
                       'raw_per_field': counts([r['raw_labels'] for r in members]),
                       'effective_per_field': counts([r['effective_labels'] for r in members]),
                       'pending_ids': [r['review_id'] for r in members if r['adjudication_status'] == 'awaiting_human_reply']})
    conflicts = [r['review_id'] for r in rows if r['execution_conflict']]
    raw_conflicts = [r['review_id'] for r in rows if r['raw_execution_conflict']]
    assert raw_conflicts == ['L005', 'L039']
    finalized = len(complete) == len(rows) and not conflicts
    result = {'status': ('complete' if finalized else 'imported_partial_completion_pending' if not conflicts else 'imported_partial_completion_and_adjudication_pending'), 'source_sha256': SHA,
              'raw_archive': raw_path.relative_to(ROOT).as_posix(), 'reviewer': raw['reviewer'],
              'reviewer_type': 'human', 'present': len(rows), 'complete': len(complete), 'partial': len(rows)-len(complete),
              'code_hashes_matched': len(rows), 'raw_complete': len(raw_complete), 'raw_partial': len(rows)-len(raw_complete),
              'raw_complete_only_counts': counts(raw_complete),
              'raw_per_field_counts': counts(list(labels.values())), 'execution_conflicts': conflicts,
              'raw_execution_conflicts': raw_conflicts,
              'effective_complete_only_counts': counts([r['effective_labels'] for r in rows if not r['missing_fields'] and r['effective_labels'].get('reason', '').strip()]),
              'effective_per_field_counts': counts(list(effective.values())),
              'missing_fields': {r['review_id']: r['missing_fields'] for r in rows if r['missing_fields']},
              'all_labels_finalized': finalized, 'applied_adjudications': applied, 'applied_completions': completions, 'groups': groups, 'rows': rows,
              'limitations': ['Raw labels preserved; no automatic change from execution or assistant notes.',
                              'Counts apply to the presampled 48, not all 72 generations.',
                              'One named reviewer for this packet; earlier packets have a different named reviewer. No overlap-based inter-rater agreement estimate.',
                              'Fresh-process passes do not refute shared-registry or same-process order dependence.',
                              'Supplemental reviewed execution never replaces primary classifications.']}
    save(ROOT / 'analysis/human_semantic_lean_v1_reconciliation.json', result)
    lines = ['精简复验人工核验导入与证据对照',
             f"复核者：{raw['reviewer']}；原导出 47 项完整，L014 缺正确性；用户明确补选后 48/48 完整，48/48 代码哈希匹配。",
             '原始 JSON 已按 SHA-256 原样存档；没有代填、修改或按执行结果覆盖人工标签。',
             '原始完整 47 项：正确 32/不符合 15；稳健 32/存在依赖 15；有意义 39/过弱或掩盖 8。',
             '原始按维度使用所有已填字段：正确性 47 项（32/15）；稳健性 48 项（33/15）；充分性 48 项（40/8）。',
             'L005、L039：原标签与执行冲突的历史记录保留；用户已裁定正确性改为不符合，其余标签不变。',
             '有效计数（裁定及补选后）：正确 31/48，不符合 17/48；稳健 33/48，有意义 40/48。',
             '两项保留的稳健性和充分性理由以补齐导入为条件；原代码未修改，不能据此计入可执行的联合有效测试。',
             'L014：用户明确补选正确性符合，补充理由另存；其余标签、原始理由和代码不变。本批无待补字段或待裁定冲突。',
             '较早的 S010/S018/S028 已由用户另行裁定；S018 的正确性为不确定，不是待回复，与本批分开统计。',
             '本批署名赵泓江，与较早何林贵批次分开；不同样本由不同人核验不能计算评审者一致率。', '',
             'AI 执行证据备注（不是第二个人工标注）：']
    lines += [f'{rid}: {note}' for rid, note in NOTES.items()]
    (ROOT / 'analysis/human_semantic_lean_v1_reconciliation.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['status', 'present', 'complete', 'partial', 'execution_conflicts', 'missing_fields']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
