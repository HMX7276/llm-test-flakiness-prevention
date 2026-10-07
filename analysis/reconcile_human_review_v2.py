"""Preserve the second human return and separately record evidence for discussion."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.import_human_review import validate
from runner.prepare import save
from runner.rule_review_status import status as rule_status

SHA='7b0e6296df82b9187d1d2ee980b855c06b064857d0babeecf7db4935508fcb1d'
FIELDS=('correctness','robustness','adequacy')


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))


def main():
    raw=ROOT/'review/semantic_v2/returned'/(SHA+'.json')
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==SHA
    payload=json.loads(raw.read_text(encoding='utf-8-sig'))
    mapping=read('review/semantic_v2/mapping_private.json')
    checked=validate(payload,mapping,expected_schema='semantic-review-v2')
    accepted=read('review/semantic_v2/accepted/'+SHA+'.json')
    assert accepted['completed']==checked['completed']
    human={r['review_id']:r for r in payload['items']}
    proposals={
        'S003':{'field':'correctness','proposed':'incorrect','kind':'concrete_missed_failure',
                 'reason':'前缀 D_ 长 2，中间长 3，后缀 _E 长 2，总长 7；原断言 len(result)==3+2 错误。主协议 30/30 fail。'},
        'S010':{'field':'correctness','proposed':'incorrect','kind':'concrete_missed_failure',
                 'reason':'最后实际差值为 2.299999999999997，不等于断言的 2.3；主协议 30/30 fail。注册表风险之外，还存在当前原代码的确定性浮点失败。'},
        'S012':{'field':'correctness','proposed':'correct','kind':'fixed_example_scope_confirmation',
                 'reason':'原代码固定 Random(42)，当前固定项目/Python 中输出 B，故 isupper() 成立；不能用“其它种子可能产生数字”推导该固定样例必错。仍只覆盖单一样例，保留弱充分性判断；不代表任意正确实现或全部随机输出。'},
        'S018':{'field':'correctness','proposed':'correct','kind':'fixed_example_scope_confirmation',
                 'reason':'当前二进制浮点中 abs(0.5-0.966)=0.46599999999999997 < 0.466，原测试 30/30 pass；“此处会失败”不符合实际。该边界写法仍脆弱且过宽，fragile/weak_or_masked 保留；正确性仅针对固定例实际值，不等于数学实数边界或充分性获认可。'},
        'S028':{'field':'correctness','proposed':'correct','kind':'fixed_example_scope_confirmation',
                 'reason':'固定 Random(42) 输出 d，or 的首分支为真，缺少 string 的第三分支没有执行。独立 AI 检查后的原文执行 30/30 pass，主协议仍是检查器拦截。缺失导入是潜在缺陷，但不能描述为本例已发生 NameError；保留 fragile/weak_or_masked 及范围局限。'},
    }
    notes={
        'S016':'有目标真实调用与字符串组装断言，故暂保留本人 meaningful。但 randint/sample 桩忽略实参，可能掩盖长度参数错误；两个手工缺陷均未检出（0/2）。应作为充分性局限，不能把稳定且有断言写成已充分检错。',
        'S019':'保留 weak_or_masked；本人理由当前说明注册表风险，尚未具体解释充分性弱点。两维不互相替代，此项不擅自重标。',
        'S024':'incorrect 有依据；实际先因未绑定 tale 名称发生 NameError，补上导入之后才可能触发本人指出的 lambda 绑定 self 问题。原始执行不能写成已到 TypeError。',
        'S007':'未绑定 fishbase 的导入错误与错误预期字符串均保留；首次实际阻断是 NameError。',
    }
    registry={'S010','S019','S022','S026','S029'}
    reviewed={r['output_id']:r['outcome'] for r in read('runs/development_v2/reviewed_execution/summary.json')['rows']}
    rows=[]
    for item in mapping:
        rid=item['review_id'];p=ROOT/item['code_path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==item['code_sha256'],rid
        assert p.read_text(encoding='utf-8')==item['code'],rid
        evaluation=json.loads((p.parent/'evaluation/summary.json').read_text(encoding='utf-8'))
        row={'review_id':rid,'output_id':item['private_output'],'target':item['target'],
             'code_path':item['code_path'],'code_sha256':item['code_sha256'],'human_raw':human[rid],
             'primary_execution':{k:evaluation.get(k) for k in ('status','counts','executions')},
             'proposal':proposals.get(rid),'adjudication_status':'pending_human_confirmation' if rid in proposals else 'no_label_change_proposed',
             'assistant_note':notes.get(rid),
             'scope_note':'保留共享注册表/套件组合风险；独立进程通过不排除此风险。' if rid in registry else None}
        if item['private_output'] in reviewed:
            posthoc=reviewed[item['private_output']]
            assert posthoc['code_sha256']==item['code_sha256']
            row['posthoc_execution']={k:posthoc.get(k) for k in ('status','counts','executions')}
        q=p.parents[1].parent/'quality'/item['private_output']/'summary.json'
        if q.exists():
            quality=json.loads(q.read_text(encoding='utf-8'))
            row['diagnostic_quality']={'killed':quality['killed'],'total':quality['total']}
        rows.append(row)
    counts={f:dict(Counter(r[f] for r in checked['completed'])) for f in FIELDS}
    decision_path=ROOT/'review/semantic_v2/adjudications/2026-10-05_response_five.json'
    responded=set(); applied=[]; conflicts=[]
    for row in rows:
        row['human_current_labels']={f:row['human_raw'][f] for f in FIELDS}
    if decision_path.exists():
        decisions=json.loads(decision_path.read_text(encoding='utf-8'))
        assert decisions['source_sha256']==SHA and decisions['reviewer']==payload['reviewer']
        assert decisions['reviewer_type']=='human'
        indexed={r['review_id']:r for r in rows}
        followup=read('runs/semantic_review_v2_followup/fresh_unperturbed/summary.json')
        evidence={r['review_id']:r for r in followup['rows']}
        for d in decisions['decisions']:
            rid=d['review_id']; row=indexed[rid]; field=d['field']
            assert rid in proposals and rid not in responded
            assert d['code_sha256']==row['code_sha256'] and d['old_value']==row['human_raw'][field]
            assert field=='correctness' and d['new_value'] in ('correct','incorrect','uncertain')
            row['human_current_labels'][field]=d['new_value']
            row['human_followup_reason']=d['human_reason']
            row['adjudication_evidence']=str(decision_path.relative_to(ROOT))
            if d['new_value']!=d['old_value']:applied.append(rid)
            row['adjudication_status']='human_response_recorded'
            if d['new_value']!=proposals[rid]['proposed']:
                conflicts.append(rid)
                assert evidence[rid]['code_sha256']==row['code_sha256']
                row['fresh_unperturbed_execution']=evidence[rid]
                row['adjudication_status']='human_label_recorded_factual_rationale_disputed'
            responded.add(rid)
    clarification_path=ROOT/'review/semantic_v2/adjudications/2026-10-05_clarification_three.json'
    held=[]
    if clarification_path.exists():
        clarification=json.loads(clarification_path.read_text(encoding='utf-8'))
        assert clarification['source_sha256']==SHA and clarification['reviewer']==payload['reviewer']
        assert clarification['apply_final_label_changes'] is False
        for item in clarification['items']:
            rid=item['review_id']; row=next(r for r in rows if r['review_id']==rid)
            assert rid in conflicts and item['code_sha256']==row['code_sha256']
            assert item['execution_facts_acknowledged'] is True
            row['human_latest_clarification']=item['human_clarification']
            row['clarification_evidence']=str(clarification_path.relative_to(ROOT))
            row['execution_fact_status']='acknowledged_by_human'
            row['adjudication_status']='historical_evidence_conflict_adjudication_pending'
            row['human_current_labels_note']='Retained pre-clarification labels, not final adjudications; latest human position recorded separately.'
            held.append(rid)
        conflicts=[rid for rid in conflicts if rid not in held]
    historical_held=list(held)
    latest_path=ROOT/'review/semantic_v2/adjudications/2026-10-05_final_three.json'
    latest_decisions=[]
    if latest_path.exists():
        latest=json.loads(latest_path.read_text(encoding='utf-8'))
        assert latest['source_sha256']==SHA and latest['actor_type']=='human'
        for item in latest['decisions']:
            rid=item['review_id'];row=next(r for r in rows if r['review_id']==rid)
            assert rid in held and item['code_sha256']==row['code_sha256']
            assert row['human_current_labels']==item['previous_effective_labels']
            assert set(item['labels'])==set(FIELDS)
            assert item['labels']['correctness'] in ('correct','incorrect','uncertain')
            row['human_current_labels']=dict(item['labels'])
            row['human_latest_adjudication_reason']=item['reason']
            row['latest_adjudication_evidence']=latest_path.relative_to(ROOT).as_posix()
            row['latest_adjudication_sha256']=hashlib.sha256(latest_path.read_bytes()).hexdigest()
            row['adjudication_status']='human_adjudicated_uncertain' if item['labels']['correctness']=='uncertain' else 'human_adjudicated'
            row['human_current_labels_note']='Explicit latest human labels; uncertain is a recorded category, not a pending response.'
            row['assistant_latest_evidence_note']=latest['assistant_evidence_notes'][rid]
            if item['labels']!=item['previous_effective_labels'] and rid not in applied:applied.append(rid)
            latest_decisions.append(item)
            held.remove(rid)
    pending=sorted(set(proposals)-responded)
    uncertain=[r['review_id'] for r in rows if r['human_current_labels']['correctness']=='uncertain']
    current_counts={f:dict(Counter(r['human_current_labels'][f] for r in rows)) for f in FIELDS}
    result={'schema':'human-semantic-reconciliation-v2','source_sha256':SHA,'source_archive':str(raw.relative_to(ROOT)),
            'reviewer':payload['reviewer'],'exported_at':payload.get('exported_at'),'imported_utc':accepted['imported_utc'],
            'complete_received':len(checked['completed']),'partial':len(checked['partial']),'not_returned':checked['not_returned'],
            'verified_code_hashes':len(rows),'raw_label_counts':counts,'pending_label_confirmation':pending,
            'human_current_label_counts':current_counts,'human_responses_recorded':sorted(responded),
            'applied_label_changes':applied,'unresolved_evidence_conflicts':conflicts,
            'held_adjudications':held,'historical_conflict_flags_retained':historical_held,
            'uncertain_correctness':uncertain,'latest_adjudications':latest_decisions,
            'latest_adjudication_evidence':latest_path.relative_to(ROOT).as_posix() if latest_path.exists() else None,
            'proposed_changes_applied':bool(applied),
            'adjudication_status':'facts_clarified_adjudication_held_by_user' if held else 'human_response_received_evidence_conflicts' if conflicts else 'pending_human_confirmation' if pending else 'resolved_with_uncertain_labels' if uncertain else 'resolved',
            'assistant_prior_notes':'notes/semantic_v2_assistant_review.txt',
            'expression_evidence':'runs/semantic_review_v2_followup/expression_evidence.json',
            'rules_v2_human_review_status':rule_status(),'agreement_coefficient':None,
            'limitations':['One human reviewer; assistant is not an independent second human.',
                           'Original labels retained; proposed changes require reviewer confirmation.',
                           'Fixed example correctness, robustness and adequacy are separate.',
                           'This return does not adjudicate RNG rule pairs or the compare-mt reference.'],
            'rows':rows}
    save(ROOT/'analysis/human_semantic_v2_reconciliation.json',result)
    lines=['第二批人工语义核验：回收与证据核对','',
           f"复核者：{payload['reviewer']}；导出时间：{payload.get('exported_at')}。",f'原始文件 SHA-256：{SHA}',
           '完整填写 36/36；部分填写 0；缺项 0；36 项原代码字节哈希与冻结映射均匹配。',
           '原始标注：正确性 22 correct / 14 incorrect；稳健性 17 robust / 19 fragile；充分性 22 meaningful / 14 weak_or_masked。',
           f'本人已回复 {len(responded)} 项，实际变更 {len(applied)} 项，待回复 {len(pending)} 项；事实仍有分歧 {len(conflicts)} 项，按本人要求保留历史冲突并暂未裁定 {len(held)} 项。原始标签保留，不能将 AI 当作第二位人类评审。',
           '当前有效标签计数（uncertain 单列，不并入符合或不符合）：'+json.dumps(current_counts,ensure_ascii=False),
           '已明确标为正确性不确定：'+str(uncertain)+'；不确定是已收到的人类判断，不是缺项或未回复。',
           '事实更正单独追加，不把通过等同于语义充分，也不覆盖原始标签或旧回复。','',
           '两项明确遗漏的执行失败，以及三项固定样例评价范围：']
    for rid,p in proposals.items():
        row=next(r for r in rows if r['review_id']==rid)
        lines.append(f"{rid}：原标签 {human[rid][p['field']]}；AI 建议 {p['proposed']}；保留标签 {row['human_current_labels'][p['field']]}；状态 {row['adjudication_status']}。{p['reason']}")
        if 'human_followup_reason' in row:lines.append('本人回复：'+row['human_followup_reason'])
        if 'human_latest_clarification' in row:lines.append('此前更正及暂缓裁定记录（历史）：'+row['human_latest_clarification'])
        if 'human_latest_adjudication_reason' in row:
            lines.append('本次明确裁定：'+json.dumps(row['human_current_labels'],ensure_ascii=False)+'；'+row['human_latest_adjudication_reason'])
            lines.append('AI 执行与源码证据（与人工标签分开）：'+row['assistant_latest_evidence_note'])
        if rid in conflicts or rid in held:lines.append('全新进程无扰动原代码复核：'+json.dumps(row['fresh_unperturbed_execution']['counts'])+'。证据 runs/semantic_review_v2_followup/fresh_unperturbed/'+rid+'/。')
    lines+=['','其余说明（不改本人标签）：']+[rid+'：'+note for rid,note in notes.items()]
    lines+=['','正确性评价需限定固定项目与解释器及原测试明确设定；执行通过本身不证明断言有充分检错能力。',
            '稳健性可另注明对共享注册表、未执行分支、版本变化等依赖；确定性错误不必同时属于 flaky。',
            '三组固定时间/随机规则已获本人保留判断；compare-mt 手工参考不因此自动获批。','',
            '逐项原始标签及主执行类别（事后执行单列于 JSON）：']
    for r in rows:
        lines.append(r['review_id']+' | '+r['output_id']+' | '+' / '.join(r['human_raw'][f] for f in FIELDS)+' | '+r['primary_execution']['status'])
    (ROOT/'analysis/human_semantic_v2_reconciliation.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('complete_received','verified_code_hashes','raw_label_counts','pending_label_confirmation')},ensure_ascii=False))


if __name__=='__main__':main()
