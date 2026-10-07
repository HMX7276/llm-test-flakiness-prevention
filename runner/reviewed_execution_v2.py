"""Post-hoc execution of individually inspected gate-rejected code, unchanged.

Not a gate relaxation, not human approval, and never overwrites primary summaries.
The explicit allowlist was reviewed for literal stdlib import / restoring dependency
patches; execution remains fresh-process with credentials removed.
"""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.development_v1 import config
from runner.evaluate import run_one,classify
IDS=['v001','v008','v011','v016','v018','v022','v025','v026','v027','v030']

if __name__=='__main__':
    run=ROOT/'runs/development_v2'; schedule=json.loads((run/'schedule.json').read_text(encoding='utf-8'))
    tasks={t['task_id']:t for t in schedule['tasks']}
    results=[]
    for cell in schedule['cells']:
        if cell['output_id'] not in IDS: continue
        src=run/'outputs'/cell['output_id']
        primary=json.loads((src/'evaluation/summary.json').read_text(encoding='utf-8'))
        assert primary['status']=='execution_review_required'
        record=json.loads((src/'record.json').read_text(encoding='utf-8'))
        path=src/'test_generated.py'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record['code_sha256']
        dest=run/'reviewed_execution'/cell['output_id']
        if (dest/'summary.json').exists():
            result=json.loads((dest/'summary.json').read_text(encoding='utf-8'))
        else:
            cfg=config(tasks[cell['task_id']])
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                runs=list(pool.map(lambda seed:run_one(path,dest/f'run_{seed:03d}',seed,cfg),range(30)))
            result=classify(runs,True)
            result.update(code_sha256=record['code_sha256'],reviewer_type='assistant',post_hoc=True,
                purpose='Original unedited code, reviewed execution only; primary unchanged; human semantics pending')
            save(dest/'executions.json',runs); save(dest/'summary.json',result)
        results.append({'output_id':cell['output_id'],'outcome':result})
        print(cell['output_id'],result['status'],result['counts'],flush=True)
    save(run/'reviewed_execution/summary.json',{'post_hoc':True,'reviewer_type':'assistant','rows':results})
