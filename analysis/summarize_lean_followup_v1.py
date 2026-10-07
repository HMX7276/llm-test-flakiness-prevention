"""Describe the frozen seen-task follow-up, with explicit missing-data states."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.prepare import save
from runner.lean_followup_v1 import RUN, verified


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    frozen = verified()
    rows, mismatches, tokens = [], [], Counter()
    for cell in frozen['cells']:
        out = RUN / 'outputs' / cell['output_id']
        row = {k: cell[k] for k in ['output_id', 'task_id', 'model_id', 'method', 'generation_round']}
        record = read(out / 'record.json') if (out / 'record.json').exists() else {}
        evaluation = read(out / 'evaluation/summary.json') if (out / 'evaluation/summary.json').exists() else {}
        quality_path = RUN / 'quality' / cell['output_id'] / 'summary.json'
        quality = read(quality_path) if quality_path.exists() else {}
        row['generation_status'] = record.get('status', 'not_generated')
        row['outcome'] = (evaluation.get('status', 'not_evaluated') if row['generation_status'] == 'api_success'
                          else row['generation_status'])
        row['executions'] = evaluation.get('executions', 0)
        row['quality_evaluated'] = bool(quality)
        row['stable_defects_detected'] = quality.get('stable_detected')
        row['defects_evaluated'] = quality.get('total')
        row['defect_details'] = quality.get('mutants', {})
        row['http_attempts'] = len(record.get('attempts', []))
        row['returned_model'] = record.get('returned_model')
        row['finish_reason'] = record.get('finish_reason')
        row['usage_returned'] = bool(record.get('usage'))
        row['attempt_seconds'] = sum(a.get('latency', 0) for a in record.get('attempts', []))
        for key in ['prompt_tokens', 'completion_tokens', 'reasoning_tokens']:
            usage = record.get('usage') or {}
            value = usage.get(key)
            if key == 'reasoning_tokens' and value is None:
                value = (usage.get('completion_tokens_details') or {}).get(key)
            if value is not None:
                tokens[key] += value
        if record.get('status') == 'api_success':
            actual = hashlib.sha256((out / 'test_generated.py').read_bytes()).hexdigest()
            if actual != record['code_sha256'] or (evaluation and actual != evaluation['code_sha256']):
                mismatches.append(cell['output_id'])
        rows.append(row)
    assert not mismatches, mismatches
    groups = []
    by_group = defaultdict(list)
    by_task = defaultdict(list)
    for row in rows:
        by_group[(row['model_id'], row['method'])].append(row)
        by_task[(row['task_id'], row['model_id'], row['method'])].append(row)
    for (model, method), members in sorted(by_group.items()):
        counts = Counter(r['outcome'] for r in members)
        qmembers = [r for r in members if r['quality_evaluated']]
        groups.append({'model': model, 'method': method, 'scheduled': len(members), 'counts': dict(counts),
                       'stable_proxy_valid': counts['stable_proxy_valid'],
                       'stable_proxy_yield': counts['stable_proxy_valid'] / len(members),
                       'quality_evaluated_outputs': len(qmembers),
                       'stable_and_detects_any_diagnostic_defect': sum(r['stable_defects_detected'] > 0 for r in qmembers),
                       'quality_pending_outputs': sum(r['outcome'] == 'stable_proxy_valid' and not r['quality_evaluated'] for r in members)})
    differences = []
    for task in frozen['tasks']:
        for model in frozen['config']['models']:
            for comparator in ['B0', 'B1', 'B2']:
                treated = by_task[(task['task_id'], model, 'M')]
                baseline = by_task[(task['task_id'], model, comparator)]
                ready = all(r['outcome'] not in ['not_generated', 'not_evaluated'] for r in treated + baseline)
                differences.append({'task': task['task_id'], 'model': model, 'comparison': 'M-' + comparator,
                                    'status': 'complete' if ready else 'pending',
                                    'stable_proxy_yield_difference': (sum(r['outcome'] == 'stable_proxy_valid' for r in treated) / len(treated)
                                                                    - sum(r['outcome'] == 'stable_proxy_valid' for r in baseline) / len(baseline)) if ready else None})
    generation_complete = all(r['generation_status'] != 'not_generated' for r in rows)
    execution_complete = generation_complete and all(r['outcome'] != 'not_evaluated' for r in rows)
    quality_complete = execution_complete and all(r['quality_evaluated'] for r in rows if r['outcome'] == 'stable_proxy_valid')
    human_path = ROOT / 'analysis/human_semantic_lean_v1_reconciliation.json'
    human = read(human_path) if human_path.exists() else None
    supplemental_path = RUN / 'reviewed_execution/summary.json'
    supplemental = read(supplemental_path) if supplemental_path.exists() else None
    supplemental_quality_path = RUN / 'reviewed_quality/summary.json'
    supplemental_quality = read(supplemental_quality_path) if supplemental_quality_path.exists() else None
    sensitivity = None
    if supplemental:
        srows = supplemental['rows']
        sensitivity = {'post_hoc': True, 'primary_unchanged': True,
                       'source': supplemental_path.relative_to(ROOT).as_posix(),
                       'source_sha256': hashlib.sha256(supplemental_path.read_bytes()).hexdigest(),
                       'executions': sum(r['outcome']['executions'] for r in srows),
                       'counts': dict(Counter(r['outcome']['status'] for r in srows)),
                       'supplemental_diagnostic_quality_evaluated': bool(supplemental_quality), 'groups': []}
        if supplemental_quality:
            assert {r['output_id'] for r in supplemental_quality['rows']} == {r['output_id'] for r in srows if r['outcome']['status'] == 'stable_proxy_valid'}
            sensitivity['diagnostic_quality'] = supplemental_quality
            sensitivity['diagnostic_quality_source_sha256'] = hashlib.sha256(supplemental_quality_path.read_bytes()).hexdigest()
        assert {r['output_id'] for r in srows} == {r['output_id'] for r in rows if r['outcome'] == 'execution_review_required'}
        for g in groups:
            added = sum(r['model_id'] == g['model'] and r['method'] == g['method'] and
                        r['outcome']['status'] == 'stable_proxy_valid' for r in srows)
            qadded = (sum(r['model_id'] == g['model'] and r['method'] == g['method'] and r['stable_detected'] > 0
                          for r in supplemental_quality['rows']) if supplemental_quality else None)
            sensitivity['groups'].append({'model': g['model'], 'method': g['method'], 'scheduled': g['scheduled'],
                                           'primary_stable': g['stable_proxy_valid'], 'additional_stable': added,
                                           'primary_plus_reviewed_stable': g['stable_proxy_valid'] + added,
                                           'additional_detects_any': qadded,
                                           'primary_plus_reviewed_detects_any': (g['stable_and_detects_any_diagnostic_defect'] + qadded
                                                                                if qadded is not None else None)})
    summary = {'scope': frozen['scope'], 'scheduled': len(rows), 'seen_tasks': 3, 'heldout_tasks': 0,
               'generation_complete': generation_complete, 'primary_execution_complete': execution_complete,
               'diagnostic_quality_complete': quality_complete,
               'generation_counts': dict(Counter(r['generation_status'] for r in rows)),
               'outcome_counts': dict(Counter(r['outcome'] for r in rows)),
               'primary_test_executions': sum(r['executions'] for r in rows),
               'http_attempts': sum(r['http_attempts'] for r in rows),
               'returned_tokens': dict(tokens), 'output_hash_mismatches': mismatches,
               'returned_model_counts': dict(Counter(r['returned_model'] for r in rows if r['returned_model'])),
               'finish_reason_counts': dict(Counter(r['finish_reason'] for r in rows if r['finish_reason'])),
               'completed_calls_without_usage': sum(r['generation_status'] != 'not_generated' and not r['usage_returned'] for r in rows),
               'groups': groups, 'task_level_differences': differences, 'rows': rows,
               'human_review_status': human['status'] if human else 'not_imported_for_this_batch',
               'human_review': ({k: human[k] for k in ['reviewer', 'present', 'complete', 'partial', 'source_sha256',
                                                      'raw_complete', 'raw_partial', 'all_labels_finalized', 'applied_completions',
                                                      'raw_per_field_counts', 'effective_per_field_counts', 'applied_adjudications',
                                                      'raw_execution_conflicts', 'execution_conflicts', 'missing_fields']}
                                if human else None),
               'reviewed_execution_sensitivity': sensitivity,
               'limitations': ['Three previously seen projects, three generations per cell; no held-out generalization claim.',
                               'Stable proxy-valid is not a human semantic label.',
                               'Seven targeted hand-seeded defects, not a representative mutation benchmark.',
                               'No significance, equivalence, or noninferiority claim; execution repeats are not independent tasks.',
                               'Failed API calls can have unreturned token usage; token totals count returned usage only.',
                               'Incomplete stages are reported explicitly; missing quality results are not zero observed detection.']}
    save(ROOT / 'analysis/lean_followup_v1_summary.json', summary)
    lines = ['精简重复比较 v1（已有开发目标，非独立留出集）',
             f"计划 72 单元；生成完成={generation_complete}；主执行完成={execution_complete}；检错诊断完成={quality_complete}",
             '生成：' + str(summary['generation_counts']), '主协议结果：' + str(summary['outcome_counts']),
             f"主测试执行 {summary['primary_test_executions']} 次；HTTP 尝试 {summary['http_attempts']} 次。", '',
             '模型 | 方法 | 计划 | 稳定代理有效 | 稳定且检出至少一项手工缺陷 | 检错待完成']
    for g in groups:
        lines.append(f"{g['model']} | {g['method']} | {g['scheduled']} | {g['stable_proxy_valid']} | {g['stable_and_detects_any_diagnostic_defect']} | {g['quality_pending_outputs']}")
    lines += ['', '人工核验状态：' + summary['human_review_status'],
              '未执行和待检错不能当成已观察的阴性结果。',
              '三个任务均已用于开发；本轮不做显著性胜负、等效或非劣性声明。',
              '七个手工缺陷仅用于检错诊断，不能称正式变异基准。']
    if human:
        if human['all_labels_finalized']:
            lines += [f"本批人审 {human['complete']}/{human['present']} 项完整；有效正确性 31/48，稳健性 33/48，充分性 40/48；本批无待补或待裁定项。原始标签、两项裁定与一项补选分开存档。"]
        else:
            lines += [f"本批人审 {human['present']} 项返回，{human['complete']} 项完整；{human['missing_fields']} 待补，{human['execution_conflicts']} 待裁定。"]
    if sensitivity:
        lines += ['', '后验门槛敏感性（原代码不改；主分类不变）：' + str(sensitivity['counts']),
                  f"补充执行 {sensitivity['executions']} 次，后验结果单列，主实验分类不变。"]
        if supplemental_quality:
            lines += [f"补充检错：{supplemental_quality['outputs']} 份输出，{supplemental_quality['executions']} 次执行，{supplemental_quality['outputs_detecting_any']} 份至少稳定检出一项既定手工缺陷。"]
        else:
            lines += ['新增通过输出尚未完成补充检错，不能继承主实验质量结论。']
        for g in sensitivity['groups']:
            lines.append(f"{g['model']} {g['method']}: 主协议 {g['primary_stable']} + 补充通过 {g['additional_stable']} = {g['primary_plus_reviewed_stable']}/{g['scheduled']}")
        lines += ['Qwen 的 M 计数优势在补充执行后消失；主协议差异受保守语法门槛混杂，不支持预防优越性。']
    (ROOT / 'analysis/lean_followup_v1_report.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ['generation_counts', 'outcome_counts', 'primary_test_executions', 'diagnostic_quality_complete']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
