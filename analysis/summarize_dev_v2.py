"""Describe v2 without pooling control checks, generation, or human labels."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.rule_review_status import status as rule_status

def read(path): return json.loads(path.read_text(encoding='utf-8'))

def main():
    run=ROOT/'runs/development_v2'; schedule=read(run/'schedule.json')
    rows=[]; mismatches=[]
    for cell in schedule['cells']:
        dest=run/'outputs'/cell['output_id']
        rec=read(dest/'record.json') if (dest/'record.json').exists() else {}
        evaluation=read(dest/'evaluation/summary.json') if (dest/'evaluation/summary.json').exists() else {}
        row={k:cell[k] for k in ['output_id','task_id','model_id','context','method']}
        row.update(status=evaluation.get('status',rec.get('status','not_attempted')),executions=evaluation.get('executions',0),
                   counts=evaluation.get('counts',{}),usage=rec.get('usage',{}),attempts=len(rec.get('attempts',[])))
        quality=run/'quality'/cell['output_id']/'summary.json'
        if quality.exists():
            q=read(quality); row['diagnostic_mutants']={'killed':q['killed'],'total':q['total']}
        assert hashlib.sha256(cell['prompt'].encode()).hexdigest()==cell['prompt_sha256']
        if rec.get('code_sha256') and hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest()!=rec['code_sha256']:
            mismatches.append(cell['output_id'])
        rows.append(row)
    controls=[]
    for task in schedule['tasks']:
        row={'task_id':task['task_id'],'project_id':task['project_id']}
        for variant in ['risk','clean','transformed']:
            p=run/'validated_controls'/task['task_id']/variant/'summary.json'
            if p.exists():
                outcome=read(p)
                source=ROOT/'data/development_v2'/task['task_id']/(variant+'.py')
                assert outcome['code_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
                row[variant]=outcome
        row['rule']=read(ROOT/'data/development_v2'/task['task_id']/'transformation.json')
        controls.append(row)
    completed_human=set()
    for p in (ROOT/'review/semantic_v1/accepted').glob('*.json'):
        completed_human.update(row['review_id'] for row in read(p).get('completed',[]))
    reconciliation_path=ROOT/'analysis/human_semantic_reconciliation.json'
    reconciliation=read(reconciliation_path) if reconciliation_path.exists() else {}
    reconciliation_v2_path=ROOT/'analysis/human_semantic_v2_reconciliation.json'
    reconciliation_v2=read(reconciliation_v2_path) if reconciliation_v2_path.exists() else {}
    groups=defaultdict(Counter)
    for row in rows: groups[(row['task_id'],row['context'],row['method'])][row['status']]+=1
    usage={key:sum((r.get('usage') or {}).get(key,0) or 0 for r in rows) for key in ['prompt_tokens','completion_tokens','reasoning_tokens']}
    result={'distinct_targets':5,'distinct_projects':5,'generated_targets':3,'planned':len(rows),
            'counts':dict(Counter(r['status'] for r in rows)),'http_attempts':sum(r['attempts'] for r in rows),
            'returned_usage':usage,'primary_executions':sum(r['executions'] for r in rows),'rows':rows,
            'groups':[{'task_id':k[0],'context':k[1],'method':k[2],'counts':dict(v)} for k,v in groups.items()],
            'controls':controls,'output_hash_mismatches':mismatches,
            'human_review':{'reviewer_plan':'user personally','completed_received':len(completed_human),
                            'status':'partial_or_complete_exports_received' if completed_human else 'awaiting_user_export',
                            'packet_scope':'48 development_v1 primary + 12 import sensitivity; excludes development_v2',
                            'pending_label_confirmation':reconciliation.get('pending_label_confirmation',[]),
                            'v1_adjudication_status':reconciliation.get('adjudication_status','not_available'),
                            'v1_effective_label_counts':reconciliation.get('effective_label_counts',{}),
                            'development_v2_review_status':reconciliation_v2.get('adjudication_status','awaiting_user_export'),
                            'development_v2_completed_received':reconciliation_v2.get('complete_received',0),
                            'development_v2_pending_label_confirmation':reconciliation_v2.get('pending_label_confirmation',[]),
                            'development_v2_evidence_conflicts':reconciliation_v2.get('unresolved_evidence_conflicts',[]),
                            'development_v2_held_adjudications':reconciliation_v2.get('held_adjudications',[]),
                            'development_v2_uncertain_correctness':reconciliation_v2.get('uncertain_correctness',[]),
                            'development_v2_effective_label_counts':reconciliation_v2.get('human_current_label_counts',{}),
                            'rules_v2_review_status':rule_status()},
            'limitations':['One generation per cell; development only','Two new RNG tasks constructed, not historical natural cases',
                           'Manual source-backed adapter metadata; no general held-out-project claim','Unsupported statistical oracle abstains',
                           'Development_v1 independent labels and post-discussion adjudications recorded separately',
                           'Development_v2 labels and their adjudication status are separate from hash-bound fixed rule-pair judgments; inspect rules_v2_review_status for current completion',
                           'Execution gate can reject otherwise valid context-manager code']}
    reviewed_path=run/'reviewed_execution/summary.json'
    if reviewed_path.exists():
        reviewed=read(reviewed_path)
        result['posthoc_reviewed_execution']={'counts':dict(Counter(r['outcome']['status'] for r in reviewed['rows'])),
            'rows':reviewed['rows'],'primary_unchanged':True,'reviewer_type':'assistant'}
    quality_groups=defaultdict(Counter)
    for row in rows:
        if 'diagnostic_mutants' in row:
            q=row['diagnostic_mutants']; quality_groups[row['task_id']][f"{q['killed']}/{q['total']}"]+=1
    result['diagnostic_quality']={key:dict(counts) for key,counts in quality_groups.items()}
    save(ROOT/'analysis/development_v2_summary.json',result)
    lines=['开发集 v2：语义核验准备、时间/随机规则、目标扩展','',
        f"人工核验：用户确认本人复核。已收到 v1 完整标签 {len(completed_human)}/60 项；待确认标签 {len(reconciliation.get('pending_label_confirmation',[]))} 项。收到标签不等于分歧裁定完成。",
        f"这 60 项为 v1 主生成 48 项及导入路径诊断 12 项；不包含本批 v2 的 36 项。另规则意图人工核验已收到 {len(rule_status()['completed'])}/3 项。详见 human_semantic_reconciliation.txt。",
        f"第二批 v2 人工标签已另行收到 {reconciliation_v2.get('complete_received',0)}/36 项，待回复 {len(reconciliation_v2.get('pending_label_confirmation',[]))} 项，执行证据冲突 {len(reconciliation_v2.get('unresolved_evidence_conflicts',[]))} 项；见 human_semantic_v2_reconciliation.txt。",
        f"待裁定：{len(reconciliation_v2.get('held_adjudications',[]))} 项；已明确标为正确性不确定：{reconciliation_v2.get('uncertain_correctness',[])}。不确定单列，不并入正确或错误，也不是未回复。",
        '开发集：5 个不同目标 / 5 个项目（计划 24）。本批仅对 Tale、RandomFileTree、fishbase 三目标进行 36 次生成。',
        '新增两随机任务是真实固定项目上的构造种子作用域案例，不是未经修改的历史 flaky 测试。','',
        '规则验证：Tale 原例 15 pass/15 fail，清理后 30/30 pass；两个随机原例各 1 pass/29 fail，清理后各 30/30 pass。',
        '清理前后 assert AST 完全相同。随机规则只采用示例既有 seed=0，不挑种子；依赖恢复和全局 RNG 不变通过 6 项真实包检查。',
        '三条转换上下文均检出其对应手工缺陷，共 7 个，每个 3 次持续失败。小样本开发检查，非正式变异得分或人类等价性判断。',
        '旧 lithoxyl 总体均值断言仍不转换；固定种子不能使错误统计 oracle 合理。','',
        '生成输出：'+json.dumps(result['counts'],ensure_ascii=False),
        f"主执行次数：{result['primary_executions']}；HTTP 尝试：{result['http_attempts']}。返回用量：{json.dumps(usage)}",'']
    for key,value in groups.items(): lines.append(' / '.join(key)+': '+json.dumps(dict(value)))
    lines.extend(['','语义复核补充：上轮 d032 的时钟读取间隙诊断为 14 pass/16 fail，原主协议 30/30 pass 保留。说明执行通过不能替代语义审查。',
        '历史案例：fishbase/tangle 隔离各 30/30 pass；freezegun 隔离通过，但显式连续两次调用第二次 30/30 fail，归入范围外共享模块状态；nxviz 缺 numpy，尚未执行到断言。',
        '无效诊断已保留并标记：v2 首轮 controls 误取旧 v1 源路径；freezegun 重复 node ID 实际只收集一次。正式本批控制结果来自 validated_controls，hash 已校验。',
        '不能从本批推断 M 普遍优于基线；单次生成、固定适配项目、构造案例、静态执行检查和待完成人工审查均限制结论。',
        '下一步：完成尚待确认的人工分歧、规则意图及 v2 人工审查；更广项目与正确性/覆盖/强基线评估；增加重复生成与项目隔离。'])
    if 'posthoc_reviewed_execution' in result:
        lines.extend(['','保守检查器拦截项的事后 AI 检查后原文执行（主结果不改写）：'+json.dumps(result['posthoc_reviewed_execution']['counts'],ensure_ascii=False),
            '这些不是新增生成或人工语义批准；说明检查器拒绝与模型测试错误必须分开。'])
    lines.extend(['','主批次通过输出的手工缺陷诊断分布：'+json.dumps(result['diagnostic_quality'],ensure_ascii=False),
        '不同任务缺陷数不同，不合并成跨项目百分比；无完整原测试套件质量基线，尚不能声称增量检错收益。'])
    (ROOT/'analysis/development_v2_report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['planned','counts','http_attempts','returned_usage','primary_executions','output_hash_mismatches']},ensure_ascii=False))
    if mismatches: raise SystemExit(1)
if __name__=='__main__': main()
