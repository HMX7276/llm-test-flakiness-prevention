"""Freeze a separate 36-item packet; do not overwrite the returned v1 packet."""
import hashlib
import json
from pathlib import Path
import random
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save


if __name__=='__main__':
    dest=ROOT/'review/semantic_v2'
    if (dest/'mapping_private.json').exists():raise SystemExit('Already frozen; no overwrite')
    run=ROOT/'runs/development_v2'
    schedule=json.loads((run/'schedule.json').read_text(encoding='utf-8'))
    tasks={t['task_id']:t for t in schedule['tasks']}
    items=[]
    for cell in schedule['cells']:
        p=run/'outputs'/cell['output_id']/'test_generated.py'
        t=tasks[cell['task_id']]
        items.append({'private_run':'development_v2','private_output':cell['output_id'],
                      'target':t['target'],'contract':t['contract'],'source':t['target_source'],
                      'code':p.read_text(encoding='utf-8'),'code_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                      'code_path':str(p.relative_to(ROOT))})
    random.Random(20261005).shuffle(items)
    mapping=[{'review_id':f'S{i:03d}',**row} for i,row in enumerate(items,1)]
    public=[{k:v for k,v in row.items() if k not in ('private_run','private_output','code_path')} for row in mapping]
    save(dest/'mapping_private.json',mapping)
    save(dest/'human_review_blank.json',{'schema':'semantic-review-v2','reviewer':'','reviewer_type':'human',
        'items':[{'review_id':r['review_id'],'code_sha256':r['code_sha256'],'correctness':'','robustness':'','adequacy':'','reason':''} for r in public]})
    template=(ROOT/'review/review_template.html').read_text(encoding='utf-8')
    html=template.replace('semantic-review-v1','semantic-review-v2').replace('llm-semantic-v1-human','llm-semantic-v2-human').replace(
        'human_semantic_review.json','human_semantic_review_v2.json').replace('测试语义核验','测试语义核验 · 第二批 36 项')
    html=html.replace('__REVIEW_DATA__',json.dumps(public,ensure_ascii=False).replace('<','\\u003c'))
    (dest/'人工语义核验.html').write_text(html,encoding='utf-8')
    (dest/'使用说明.txt').write_text('第二批独立核验包，共 36 项 S001—S036；对应 development_v2，不重复前 60 项。\n模型、方法、执行结果和 AI 判断隐藏。先评价未修改的原代码，包括导入、期望值与风险。\n可分多次保存；导出 human_semantic_review_v2.json 后交给助手。此页面暂存键与第一批不同。\nAI 说明留在 notes/semantic_v2_assistant_review.txt，独立判断前无需查看。\n',encoding='utf-8')
    print('Frozen 36 items; no human labels prefilled.')
