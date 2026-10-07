import collections
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

def main():
    run=ROOT/'runs/development_v1'
    schedule=json.loads((run/'schedule.json').read_text(encoding='utf-8'))
    rows=[]
    mismatches=[]
    for cell in schedule['cells']:
        dest=run/'outputs'/cell['output_id']
        row={k:cell[k] for k in ['output_id','task_id','model_id','context','method']}
        record=json.loads((dest/'record.json').read_text(encoding='utf-8')) if (dest/'record.json').exists() else {}
        row.update(status=record.get('status','not_attempted'),attempts=len(record.get('attempts',[])),usage=record.get('usage') or {})
        summary=dest/'evaluation/summary.json'
        if summary.exists():
            evaluation=json.loads(summary.read_text(encoding='utf-8'))
            row.update(status=evaluation['status'],executions=evaluation['executions'],counts=evaluation['counts'])
        quality=run/'quality'/cell['output_id']/'summary.json'
        if quality.exists():
            q=json.loads(quality.read_text(encoding='utf-8'))
            row['diagnostic_mutants']={'killed':q['killed'],'total':q['total']}
        if record.get('code_sha256') and hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest()!=record['code_sha256']:
            mismatches.append(cell['output_id'])
        assert hashlib.sha256(cell['prompt'].encode()).hexdigest()==cell['prompt_sha256']
        rows.append(row)
    groups=collections.defaultdict(collections.Counter)
    for row in rows: groups[row['task_id']][row['status']]+=1
    result={'planned':len(rows),'distinct_targets':3,'projects':3,'counts':dict(collections.Counter(r['status'] for r in rows)),
        'by_task':{k:dict(v) for k,v in groups.items()},'http_attempts':sum(r['attempts'] for r in rows),
        'returned_usage':{key:sum(r['usage'].get(key,0) or 0 for r in rows) for key in ['prompt_tokens','completion_tokens','reasoning_tokens']},
        'primary_execution_count':sum(r.get('executions',0) for r in rows),'output_hash_mismatches':mismatches,
        'rows':rows,'interpretation':'Controlled development diagnostic; 1 generation per cell; human semantic review pending. M abstains on time/randomness. No significance or superiority inference.'}
    quality_groups=collections.defaultdict(collections.Counter)
    for row in rows:
        if 'diagnostic_mutants' in row:
            q=row['diagnostic_mutants']
            quality_groups[row['task_id']][f"{q['killed']}/{q['total']}"]+=1
    result['diagnostic_mutant_distribution']={k:dict(v) for k,v in quality_groups.items()}
    sensitivity=[]
    for path in (ROOT/'runs/development_v1_import_sensitivity/outputs').glob('*/record.json'):
        rec=json.loads(path.read_text(encoding='utf-8'))
        summary=path.parent/'evaluation/summary.json'
        outcome=json.loads(summary.read_text(encoding='utf-8')) if summary.exists() else {'status':rec['status']}
        sensitivity.append({'output_id':path.parent.name,'task_id':rec['task_id'],'outcome':outcome,
                            'usage':rec.get('usage',{}),'attempts':len(rec['attempts'])})
    result['import_path_sensitivity']={'counts':dict(collections.Counter(r['outcome']['status'] for r in sensitivity)),
                                      'rows':sensitivity,'post_hoc':True}
    save(ROOT/'analysis/development_v1_summary.json',result)
    lines=['开发集 v1 诊断报告（2026-10-05）','',f"规模：3 个不同目标 / 3 个项目；48 个计划生成单元；实际 HTTP 尝试 {result['http_attempts']}。",
        '来源：PENMAN 人工构造；Tale 历史风险改编；lithoxyl 历史启发的人工构造。不是 3 个未经修改的自然 flaky 案例。',
        '受控运行：每份可执行输出 30 个新进程；hash、入口随机状态、交替调度延迟按任务类型施加。不是生产中的自然发生率。','',
        '输出分类：'+json.dumps(result['counts'],ensure_ascii=False),f"主执行次数：{result['primary_execution_count']}",'']
    for key,counts in groups.items(): lines.append(key+': '+json.dumps(dict(counts),ensure_ascii=False))
    lines.extend(['','返回用量（不含失败请求可能发生的不可见消耗）：'+json.dumps(result['returned_usage']),
        '人工语义审查仍待完成；稳定代理有效仅表示静态代理、实际调用和 30 次全通过。',
        '变异结果为事后手工诊断，不是正式变异得分；不同目标的变异体数量不同，不合并成跨项目百分比。',
        'M 对随机/时间风险保持原文，因此这些任务的 M 与 B0 是相同提示的另一次生成；差异不能归因于清理算法。',
        'B2 删除示例后 risk/clean 提示相同，不能当作独立上下文处理。每单元只有一次生成，不作显著性检验。',
        '两模型均成功关闭思考（按返回报告）；请求长度上限 32 的六次探测均未被遵守。采样参数及模型权重版本未独立验证。'])
    lines.append('提示缺陷：目标完整导入路径只出现在部分示例中，B2 删除示例后 lithoxyl 的正确导入路径不足；B2 的导入失败混合了这一因素。单独追加路径明确化敏感性分析，不改写主结果。')
    lines.append('语义核查提醒：d032 虽 30 次全通过，但仍把两次真实时钟读数视作相等；当前扰动没有覆盖两次读取之间的调度间隙。不能将所有通过项称为语义合格。详见 notes/development_v1_assistant_review.txt。')
    lines.extend(['','独立导入路径敏感性（不替换主结果）：'+json.dumps(result['import_path_sensitivity']['counts'],ensure_ascii=False),
        '该敏感性补充了导入信息并重新生成，不能当作对同一代码的修复效果；剩余断言/名称错误全部保留。',
        '手工变异诊断分布（通过输出，键为检出数/变异体数）：'+json.dumps(result['diagnostic_mutant_distribution'],ensure_ascii=False),
        '历史候选核验：新增 5 个项目，未发现新的普通隔离混合结果；Tale 和 lithoxyl 仅在明确控制扰动下显示敏感性。详见 data/curation_v1.json。',
        'd003 额外普通隔离 30/30 pass，与主协议调度延迟 15 pass/15 fail 相对照。不能从单份生成推断因果或方法优越性。',
        '本轮 API 共 66 次：6 次参数校准 + 48 次主生成 + 12 次导入路径诊断；均有返回，按用户说明货币费用为零。',
        '当前开发集 3/24 个计划目标；正式数据集、独立人工标注及论文主实验尚未完成。'])
    (ROOT/'analysis/development_v1_report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['rows','interpretation']},ensure_ascii=False))
    if mismatches: raise SystemExit(1)
if __name__=='__main__': main()
