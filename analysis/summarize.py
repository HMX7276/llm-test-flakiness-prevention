"""Offline reconstruction of all planned cells, including missing/failed calls."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save


def main():
    run=ROOT/'runs/pilot_v0'
    frozen=json.loads((run/'schedule.json').read_text())
    rows=[]
    for cell in frozen['cells']:
        dest=run/'outputs'/cell['output_id']
        row={k:cell[k] for k in ['output_id','model_id','context_condition','method','generation_round']}
        row.update({'task_id':frozen['config']['task_id'],'status':'not_completed','executions':0,
                    'has_pass':False,'prompt_tokens':0,'completion_tokens':0,'attempt_count':0,
                    'retry_count':0,'tokens_missing_for_attempts':0,'latency':0})
        if (dest/'record.json').exists():
            record=json.loads((dest/'record.json').read_text())
            row['status']=record['status']
            row['attempt_count']=len(record['attempts'])
            row['retry_count']=record['retry_count']
            row['tokens_missing_for_attempts']=sum(a['status']!='ok' for a in record['attempts'])
            row['latency']=sum(a['latency'] for a in record['attempts'])
            usage=record.get('usage',{})
            row['prompt_tokens']=usage.get('prompt_tokens',0)
            row['completion_tokens']=usage.get('completion_tokens',0)
            row['reasoning_tokens']=usage.get('reasoning_tokens',0)
            row['returned_model']=record.get('returned_model')
            if (dest/'test_generated.py').exists():
                actual=hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest()
                assert actual==record['code_sha256'],f"Generated artifact changed: {dest.name}"
            if (dest/'evaluation/summary.json').exists():
                evaluation=json.loads((dest/'evaluation/summary.json').read_text())
                assert evaluation['code_sha256']==record['code_sha256']
                row.update({k:evaluation[k] for k in ['status','executions','counts']})
                row['has_pass']=evaluation.get('has_pass',False)
            if (dest/'quality/summary.json').exists():
                quality=json.loads((dest/'quality/summary.json').read_text())
                row['diagnostic_mutants_killed']=quality['killed']
                row['diagnostic_mutants_total']=quality['mutant_denominator']
                row['coverage']=quality['coverage'].get('target_summary')
        rows.append(row)
    groups=defaultdict(list)
    for row in rows:
        groups[(row['model_id'],row['context_condition'],row['method'])].append(row)
    grouped=[]
    for (model,ctx,method),items in sorted(groups.items()):
        counts=Counter(i['status'] for i in items)
        eligible=sum(i['has_pass'] for i in items)
        grouped.append({'model':model,'context':ctx,'method':method,'planned':len(items),
                        'states':dict(counts),'at_least_one_pass':eligible,
                        'observed_unstable_rate':counts['observed_unstable']/eligible if eligible else None,
                        'stable_proxy_yield':counts['stable_proxy_valid']/len(items)})
    summary={'experiment':frozen['config']['experiment_id'],'independent_tasks':1,
             'planned_outputs':len(rows),'states':dict(Counter(r['status'] for r in rows)),
             'total_test_executions':sum(r['executions'] for r in rows),
             'http_attempts':sum(r['attempt_count'] for r in rows),
             'returned_prompt_tokens':sum(r['prompt_tokens'] for r in rows),
             'returned_completion_tokens':sum(r['completion_tokens'] for r in rows),
             'attempts_with_unknown_token_cost':sum(r['tokens_missing_for_attempts'] for r in rows),
             'currency_cost_to_user':0,'currency_cost_basis':'User reports free school API access',
             'rows':rows,'groups':grouped,
             'limitations':['Single development task; no inferential statistics.',
                            'Stable proxy validity is not human semantic validation.',
                            'Hash sweep does not estimate ordinary CI incidence.',
                            'Four hand-seeded mutants are only development diagnostics.',
                            'API aliases do not pin weights; provider defaults differ between models.']}
    sensitivity_path=ROOT/'analysis/format_sensitivity.json'
    if sensitivity_path.exists():
        sensitivity=json.loads(sensitivity_path.read_text())
        summary['post_hoc_presentation_sensitivity']={
            'changed_outputs':len(sensitivity['changed_outputs']),
            'states':dict(Counter(r['evaluation']['status'] for r in sensitivity['changed_outputs']))}
    save(ROOT/'analysis/pilot_v0_summary.json',summary)
    lines=['首个开发任务实验报告','',
           f"独立目标任务：1；计划输出：{len(rows)}；测试重复执行：{summary['total_test_executions']}。",
           '当前互斥状态：'+json.dumps(summary['states'],ensure_ascii=False),
           f"API 请求尝试：{summary['http_attempts']}；已返回输入 token：{summary['returned_prompt_tokens']}；已返回输出 token：{summary['returned_completion_tokens']}。",
           f"{summary['attempts_with_unknown_token_cost']} 次失败请求没有返回用量，上述 token 为可观测下界。用户确认学校 API 免费。",'',
           '每格只有两个生成重复；所有格属于同一个目标函数，不能进行跨项目推断。',
           'stable_proxy_valid 表示 30 次全通过、存在断言并实际调用目标函数；人工语义审查尚未完成。','',
           '模型 | 上下文 | 方法 | 计划数 | 状态']
    for g in grouped:
        lines.append(f"{g['model']} | {g['context']} | {g['method']} | {g['planned']} | {json.dumps(g['states'],ensure_ascii=False)}")
    lines += ['', '解释与下一步',
              '1. 风险控制示例为 15 pass / 15 fail，clean 和自动清理示例均 30 pass；执行器具备该风险检测能力。',
              '2. 原 PENMAN 测试已覆盖目标全部分支，且检出全部四个开发变异体。此任务不能证明新增覆盖或变异收益。',
              '3. 原始输出、格式失败、超时和重试均保留；不因结果不理想重采样。',
              '4. PENMAN 旧版与修复版各 30 次整套运行全通过。fparser 单独运行 30 次全失败；特定前置测试先执行时 30 次全通过，反向执行时 30 次全失败。已定位测试顺序/共享缓存依赖，单列为范围外诊断。',
              '5. 扩展前要增加任务复杂度和项目多样性，核查自然风险证据；不能通过重复这个简单函数凑样本。',
              '6. 待本批全部完成后，确认输出提取规则、API 超时/思考模式、自动规则适用范围，再开新开发批次。']
    if summary.get('post_hoc_presentation_sensitivity'):
        lines += ['', '格式敏感性分析（事后分析，不覆盖主结果）',
                  json.dumps(summary['post_hoc_presentation_sensitivity'],ensure_ascii=False),
                  '仅统一移除首尾 Markdown 围栏，未改测试逻辑；详见 analysis/format_sensitivity.json。']
    (ROOT/'analysis/pilot_v0_report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['rows','groups','limitations']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
