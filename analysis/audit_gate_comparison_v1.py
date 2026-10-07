"""Reconcile primary versus post-hoc execution counts without changing results."""
from collections import Counter
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'analysis/lean_followup_v1_summary.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    supplement_path = ROOT / data['reviewed_execution_sensitivity']['source']
    supplemental = json.loads(supplement_path.read_text(encoding='utf-8'))
    assert hashlib.sha256(supplement_path.read_bytes()).hexdigest() == data['reviewed_execution_sensitivity']['source_sha256']
    rows = data['rows']
    held = {r['output_id'] for r in rows if r['outcome'] == 'execution_review_required'}
    assert held == {r['output_id'] for r in supplemental['rows']}
    assert len(held) == len(supplemental['rows']) == 15
    primary_ids = {r['output_id'] for r in rows if r['outcome'] == 'stable_proxy_valid'}
    assert not primary_ids & held
    groups = []
    for g in data['groups']:
        model, method = g['model'], g['method']
        sub = [r for r in rows if (r['model_id'], r['method']) == (model, method)]
        extra = [r for r in supplemental['rows'] if (r['model_id'], r['method']) == (model, method)]
        counts = Counter(r['outcome'] for r in sub)
        stable = counts['stable_proxy_valid']
        added = sum(r['outcome']['status'] == 'stable_proxy_valid' for r in extra)
        detected = sum(r['quality_evaluated'] and (r['stable_defects_detected'] or 0) > 0 for r in sub)
        assert len(sub) == g['scheduled'] == 9
        assert stable == g['stable_proxy_valid']
        assert detected == g['stable_and_detects_any_diagnostic_defect']
        groups.append(dict(model=model, method=method, scheduled=len(sub), held=len(extra), primary_stable=stable,
                           supplemental_stable=added, combined_stable=stable+added, primary_stable_and_detects_any=detected))
    assert sum(g['primary_stable'] for g in groups) == 32
    assert sum(g['supplemental_stable'] for g in groups) == 14
    quality = data['reviewed_execution_sensitivity']['diagnostic_quality']['rows']
    assert {r['output_id'] for r in quality} == {r['output_id'] for r in supplemental['rows'] if r['outcome']['status'] == 'stable_proxy_valid'}
    assert len(quality) == 14 and all(r['stable_detected'] > 0 for r in quality)
    report = dict(scope='Reconciliation of existing records; no new executions or generations',
                  primary_unchanged=True, primary_scheduled=72, primary_stable=32,
                  supplemental_stable=14, pooled_stable=46, primary_detects_any=31,
                  pooled_detects_any=45, groups=groups,
                  source_sha256={str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                                 for f in (source, supplement_path)},
                  limitation='Post-hoc execution review is not a prospectively uniform gate; pooled counts remain sensitivity results.')
    (ROOT/'analysis/gate_comparison_audit_v1.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    lines = ['执行门槛公平对比核对（既有证据复核；未新增实验）',
             '各组分母均为 9 个计划生成单元，原主结果与后验补充分别保留。',
             '模型 | 方法 | 主协议稳定通过 | 门槛拦截 | 补充稳定通过 | 合计稳定通过',
             *[f"{g['model']} | {g['method']} | {g['primary_stable']}/9 | {g['held']} | {g['supplemental_stable']} | {g['combined_stable']}/9" for g in groups],
             '', '结论：Qwen 的 M 计数优势在补充执行后消失。DeepSeek 的描述性差异仍不能证明跨项目优越性。',
             '原主协议稳定且检出至少一项手工缺陷为 31/72；在主协议稳定通过输出中为 31/32。',
             '后验合计对应 45/72、45/46；这些是不同条件分母，不得混写为同一个成功率。',
             '全部 15 项拦截均有补跑记录，不存在只挑通过项补跑；14 项补充通过均有既定缺陷诊断。',
             '后验放行不等于已经完成统一门槛的前瞻实验。三个目标均已用于开发，不能称独立测试集。',
             '', '下一步：在新目标生成前固定所有方法共用的执行审查标准、人工放行标准和失败处理；',
             '限定少量新项目，先记录候选与排除依据，再冻结任务、代码、缺陷与提示；保留不适用及阴性结果。']
    (ROOT/'analysis/gate_comparison_audit_v1.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8-sig')
    print('Verified all 72 primary rows, all 15 gate-held outputs, eight groups, and 14 supplemental diagnostic records.')


if __name__ == '__main__':
    main()
