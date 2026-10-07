"""Offline blinded human review packet. AI judgments never prefill human fields."""
import hashlib
import json
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

ISSUES={
 'd001':('invalid','monkeypatch.attr does not exist; clock sequence inconsistent; gate also rejects Try and weakref.'),
 'd003':('fragile','Live-clock post-send bound; 15/15 under controlled delay, 30/30 unperturbed.'),
 'd005':('invalid','Three equally spaced observations have Pearson kurtosis 1.5, not 1.6666667.'),
 'd011':('invalid','Clock substitution occurs after creation; last_event retains real time.'),
 'd015':('invalid','Queued event and synchronous event both delivered; expected one response but there are two.'),
 'd017':('invalid','Wrong import path; class is in lithoxyl.moment.'),
 'd018':('invalid','Wrong import path; further numeric assertions need independent review.'),
 'd025':('invalid','Expected skewness and kurtosis constants do not match finite sample formulas.'),
 'd032':('fragile','Assumes separate wall-clock reads are identical. Primary all-pass does not cover read-to-read gap.'),
 'd033':('invalid','Asserts historical real last_event<100 after clock substitution.'),
 'd036':('invalid','Wrong import path; class is in lithoxyl.moment.'),
 'd038':('invalid','Treats target-only identifier y as a graph source variable.'),
 'd041':('invalid','Asserts population variance rather than documented sample variance and wrong higher moments.'),
 'd046':('review_internal_state','Writes last_event directly; reset assertion still exercises send, construction check is masked.'),
 'd047':('invalid','Wrong import path; class is in lithoxyl.moment.'),
 'd048':('invalid','Substitutes a function where implementation needs a time module with time().')}
SENS_ISSUES={
 'd011':('invalid','Clock substituted after creation.'),
 'd018':('invalid','Unimported statistics; statistics.skew/kurtosis are also not standard APIs.'),
 'd033':('invalid','Unimported types used for SimpleNamespace.'),
 'd036':('invalid','Symmetric two-valued sample has Pearson kurtosis 1, not 1.6666667.')}

def main():
    dest=ROOT/'review/semantic_v1'
    if (dest/'mapping_private.json').exists():
        raise SystemExit('Review packet already frozen; preserve reviewer correspondence')
    items=[]; labels=[]
    for run_name in ['development_v1','development_v1_import_sensitivity']:
        run=ROOT/'runs'/run_name
        schedule=json.loads((run/'schedule.json').read_text(encoding='utf-8'))
        tasks={t['task_id']:t for t in schedule['tasks']}
        for cell in schedule['cells']:
            path=run/'outputs'/cell['output_id']/'test_generated.py'
            if not path.exists(): continue
            task=tasks[cell['task_id']]
            items.append({'private_run':run_name,'private_output':cell['output_id'],
                'target':task['target'],'contract':task['contract'],'source':task['target_source'],
                'code':path.read_text(encoding='utf-8'),'code_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'code_path':str(path.relative_to(ROOT))})
    random.Random(20261006).shuffle(items)
    mapping=[]; public=[]
    for i,item in enumerate(items):
        rid=f'R{i+1:03d}'
        mapping.append({'review_id':rid,**item})
        public.append({k:v for k,v in {'review_id':rid,**item}.items() if k not in ['private_run','private_output','code_path']})
        issues=ISSUES if item['private_run']=='development_v1' else SENS_ISSUES
        verdict,reason=issues.get(item['private_output'],('provisionally_sound',
            'Assistant source/contract inspection found no specific semantic defect; coverage and adequacy remain separate. Human confirmation required.'))
        labels.append({'review_id':rid,'ai_verdict':verdict,'ai_reason':reason,'reviewer_type':'assistant',
                       'human_verdict':None,'human_review_status':'pending'})
    save(dest/'mapping_private.json',mapping)
    save(dest/'ai_assessment_separate.json',labels)
    save(dest/'human_review_blank.json',{'schema':'semantic-review-v1','reviewer':'','reviewer_type':'human',
         'items':[{'review_id':i['review_id'],'code_sha256':i['code_sha256'],'correctness':'','robustness':'',
                   'adequacy':'','reason':''} for i in public]})
    payload=json.dumps(public,ensure_ascii=False).replace('<','\\u003c')
    html=(ROOT/'review/review_template.html').read_text(encoding='utf-8').replace('__REVIEW_DATA__',payload)
    (dest/'人工语义核验.html').write_text(html,encoding='utf-8')
    (dest/'使用说明.txt').write_text('请先打开 人工语义核验.html。共 60 份测试，模型/方法/运行结果及 AI 判断隐藏。\n填写你的名字或代号，逐项标注正确性、稳健性、充分性和理由；允许“不确定”。\n页面尽力在本机浏览器保存；请定期点击导出，保存 JSON 文件以防浏览器缓存丢失。\n每份测试独立判断：不因其它项相似而跳过。先独立判断，再查看 ai_assessment_separate.json 对照。\n完成后将导出的 JSON 放入 review/semantic_v1/returned/，我会检查文件与代码哈希并整理分歧。\n你本人是人类复核者；AI 不是第二位人类，不计算双人一致性系数。\n',encoding='utf-8')
    print('Created',len(public),'blinded items; human labels empty')
if __name__=='__main__': main()
