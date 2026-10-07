"""Separate upstream baselines, candidate screening, and manual-pair diagnostics."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.rule_review_status import status as rule_status


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))


def main():
    v2_path=ROOT/'analysis/human_semantic_v2_reconciliation.json'
    v2_review=json.loads(v2_path.read_text(encoding='utf-8')) if v2_path.exists() else {}
    baseline=read('runs/upstream_baseline_v3/summary.json')
    baselines=[]
    for project in baseline['projects']:
        mutants={name:{'stable_detection':r['detected_by_same_original_node_all_three'],
                        'valid_comparison':r['valid_comparison'],
                        'any_detection':any(any(s=='fail' for s in x['cases'].values()) for x in r['runs'])}
                 for name,r in project['mutants'].items()}
        baselines.append({'project_id':project['project_id'],'scope':project['scope'],
                          'original_counts':[r['counts'] for r in project['originals']],
                          'full_collection':project['collection']['status'],'mutants':mutants})
    followup=read('runs/upstream_baseline_v3/fishbase/length_followup_30.json')
    fish_counts={k:dict(Counter(r['status'] for r in v)) for k,v in followup['runs'].items()}
    joined=[]
    for run_name in ['development_v1','development_v2']:
        schedule=read(f'runs/{run_name}/schedule.json')
        task_project={t['task_id']:t['project_id'] for t in schedule['tasks']}
        for cell in schedule['cells']:
            p=ROOT/'runs'/run_name/'quality'/cell['output_id']/'summary.json'
            if not p.exists():continue
            generated=json.loads(p.read_text(encoding='utf-8'))
            project=next(p for p in baselines if p['project_id']==task_project[cell['task_id']])
            kills={k for k,v in generated['mutants'].items() if v['killed']}
            original_ever={k for k,v in project['mutants'].items() if v['any_detection']}
            original_stable={k for k,v in project['mutants'].items() if v['stable_detection']}
            joined.append({'run':run_name,'output_id':cell['output_id'],'project_id':project['project_id'],
                           'original_scope':project['scope'],'generated_killed':sorted(kills),
                           'additional_over_ever_detected':sorted(kills-original_ever),
                           'additional_over_three_of_three':sorted(kills-original_stable)})
    candidates=[]
    for name in ['kevinarpe-rambutan3','grabbit']:
        r=read(f'runs/curation_v3_initial/{name}/summary.json')
        candidates.append({'project':r['candidate']['project'],'commit':r['candidate']['commit'],
                           'counts':r['counts'],'test':r['candidate']['test'],
                           'status':'product_hash_contract_violation_excluded' if name.startswith('kevinarpe') else 'not_reproduced',
                           'evidence':f'runs/curation_v3_initial/{name}/summary.json','formal_eligible':False})
    inc=read('runs/curation_v3_grabbit_include/summary.json')
    candidates.append({'project':inc['candidate']['project'],'commit':inc['candidate']['commit'],
                       'test':inc['candidate']['test'],'counts':inc['counts'],'status':'not_reproduced','formal_eligible':False,
                       'evidence':'runs/curation_v3_grabbit_include/summary.json'})
    cmp=read('runs/curation_v3_scientific/compare-mt/summary.json')
    candidates.append({'project':cmp['candidate']['project'],'commit':cmp['candidate']['commit'],'test':cmp['candidate']['test'],
                       'counts':cmp['counts'],'status':'not_reproduced','formal_eligible':False,
                       'evidence':'runs/curation_v3_scientific/compare-mt/summary.json',
                       'retained_setup_probes':['runs/curation_v3_initial/compare-mt/summary.json','runs/curation_v3_compare/summary.json']})
    pair=read('runs/compare_mt_pair_probe_v3/summary.json')
    validation=read('runs/compare_mt_pair_validation_v3/summary.json')
    for variant,r in pair['outcomes'].items():
        p=ROOT/'data/candidate_tasks_v3/compare_mt_bootstrap_cache_001'/(variant+'.py')
        assert hashlib.sha256(p.read_bytes()).hexdigest()==r['code_sha256']
    assert pair['outcomes']['risk']['counts']=={'fail':28,'pass':2}
    assert pair['outcomes']['manual_clean']['counts']=={'pass':30}
    old=read('data/development_v2/index.json')
    entries=[{**t,'task_path':f"data/development_v2/{t['task_id']}/task.json"} for t in old['tasks']]
    entries.append({'task_id':pair['task']['task_id'],'target':pair['task']['target'],'project_id':'compare-mt',
                    'dataset_layer':'historical_inspired_constructed','human_review_status':'pending',
                    'task_path':'data/candidate_tasks_v3/compare_mt_bootstrap_cache_001/task.json',
                    'automatic_method_support':'unsupported_by_M_v2','generation_status':'not_scheduled',
                    'manual_pair_evidence':'runs/compare_mt_pair_probe_v3/summary.json'})
    save(ROOT/'data/development_v3/index.json',{'distinct_targets':6,'distinct_projects':6,'tasks':entries,
        'formal_dataset':False,'planned_development_targets':24,
        'scope':'Development registry only. The sixth target has a manual reference; no frozen generation schedule or automatic-rule success is implied.'})
    result={'baselines':baselines,'fishbase_length_followup_30':fish_counts,
            'generated_quality_comparison':joined,'candidate_screening':candidates,
            'new_manual_pair':{'task':pair['task'],'counts':{k:r['counts'] for k,r in pair['outcomes'].items()},
                               'validation':{k:r['counts'] for k,r in validation['results'].items()}},
            'development_targets':6,'rule_human_review':rule_status(),'new_api_calls':0,
            'v2_review_packet':'review/semantic_v2/人工语义核验.html','v2_human_reviews_received':v2_review.get('complete_received',0),
            'v2_pending_label_confirmation':v2_review.get('pending_label_confirmation',[]),
            'v2_evidence_conflicts':v2_review.get('unresolved_evidence_conflicts',[]),
            'v2_held_adjudications':v2_review.get('held_adjudications',[]),
            'v2_uncertain_correctness':v2_review.get('uncertain_correctness',[]),
            'limitations':['Original subsets for four projects; only PENMAN full suite executed.',
                           'Hand-seeded defects and small development samples; no formal significance or superiority claim.',
                           'The historical compare-mt test itself did not reproduce; the new target is an explicit adaptation.',
                           'No human approval for the new cache-pair reference yet; NumPy replay not implemented in M v2.',
                           'Original frozen generated tests and execution records unchanged.']}
    save(ROOT/'data/curation_v3.json',{'records':candidates,'new_constructed_target':pair['task']['task_id']})
    save(ROOT/'analysis/followup_v3_summary.json',result)
    lines=['人工核验后的下一阶段：质量基线与第三轮候选核验','',
        '开发诊断目标 6/24，来自 6 个项目。新增 compare-mt 的手工成对缓存参考，不代表现有自动规则已支持，也未开始该目标的模型生成。',
        '本轮无新增 API 调用；优先补实验对照和真实源码证据。','',
        '原测试检错基线（3 个独立进程；仅在原节点持续通过且缺陷版同节点持续失败时计稳定检出）：']
    for p in baselines:
        lines.append(f"{p['project_id']} | {p['scope']} | 原测试 {p['original_counts']} | 稳定检出 {sum(v['stable_detection'] for v in p['mutants'].values())}/{len(p['mutants'])} | 全套收集 {p['full_collection']}")
    lines.extend(['',
        'Tale 全套收集缺 smartypants/appdirs/serpent；RandomFileTree、fishbase、lithoxyl 全套收集成功不等于已执行全套。',
        'fishbase 长度缺陷补充 30 次：原实现 30 pass；缺陷版 25 pass/5 fail。首批 3 次为 2 pass/1 fail，原记录保留。',
        f'对已有 {len(joined)} 份主协议通过输出的手工缺陷结果做交叉核对，没有发现原测试子集从未检出而生成测试新检出的缺陷。',
        'fishbase 的 v012/v019 各在 3 次缺陷检查中全部检出长度错误，原测试检出不稳定；可作为检错可靠性线索，不能当作正式方法优势或新的缺陷数量。',
        'RandomFileTree 的 constant_chars 缺陷，原目标测试和本批两个主协议通过生成输出均未检出。','',
        '新候选：',
        'rambutan3：历史原节点 3 pass/27 fail。失败违反等价对象应有相同哈希的产品契约；super(object,self).__hash__ 实际绑定临时 super 代理。不能通过删除断言将产品错误洗成稳定测试。',
        '哈希契约来源：https://docs.python.org/3.11/reference/datamodel.html#object.__hash__ 。根因诊断见 runs/curation_v3_initial/kevinarpe-rambutan3/root_cause.json。',
        'grabbit：include/exclude 两个本地节点各 30/30 pass；未复现，不算新增自然风险目标。',
        'compare-mt：原历史节点 30/30 pass；最初缺 numpy、随后 NLTK 缓存目录缺失两次环境问题均保留。独立环境及本地缓存配置后执行，不改旧实验环境。','',
        '新增 compare-mt 改编目标：',
        '固定四条小语料、单词 BLEU、每次 5 次 bootstrap；显式缓存路径和内部计算缓存路径独立抽样时，风险参考 2 pass/28 fail。',
        '手工参考用局部 NumPy RandomState 从入口状态克隆，并在第二路径前重放同一状态：30/30 pass。两条断言 AST 均保留，不挑种子（固定入口 0..29）。',
        '全局 NumPy 状态与模块依赖恢复检查 3/3 pass；反转缓存、重复首缓存两个手工缺陷各 2 fail/1 pass，保留未检出结果。',
        '源码另有 wins 统计分支问题，缓存等价性断言不验证统计量本身正确性；这不能写成整个 bootstrap 算法已被核验正确。','',
        f"人工进度：v1 的 60 项及 5 项调整已记录；固定规则意图收到 {len(rule_status()['completed'])}/3 项（逐项判断见 rule_human_review）；第二批已收到 {v2_review.get('complete_received',0)}/36 项，待回复 {len(v2_review.get('pending_label_confirmation',[]))} 项，执行证据冲突 {len(v2_review.get('unresolved_evidence_conflicts',[]))} 项。",
        f"待裁定 {len(v2_review.get('held_adjudications',[]))} 项；明确正确性不确定 {v2_review.get('uncertain_correctness',[])}。历史冲突记录保留，最新标签另存。",
        '下一步按 notes/two_week_delivery_plan.txt 收敛；四组重复生成及其补充检错已完成，当前结果见 lean_followup_v1_report.txt；暂缓 NumPy 泛化。'])
    (ROOT/'analysis/followup_v3_report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'targets':6,'projects':6,'baseline_projects':len(baselines),'quality_outputs_joined':len(joined),
                      'newly_detected_over_original_any':sum(bool(r['additional_over_ever_detected']) for r in joined),
                      'rules_received':len(rule_status()['completed'])},ensure_ascii=False))


if __name__=='__main__':main()
