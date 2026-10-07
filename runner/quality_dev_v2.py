"""Task-specific diagnostic mutants for stable v2 outputs, separate from controls."""
import concurrent.futures
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.development_v1 import config
from runner.evaluate import evaluate
from runner.rule_validation_v2 import paths

def assess(cell,task,mutants):
    base=ROOT/'runs/development_v2'
    out=base/'outputs'/cell['output_id']
    results={}
    for name,project in mutants.items():
        cfg={**config(task),'project_path':str(project),'hash_seeds':[0,1,2]}
        result=evaluate(out/'test_generated.py',base/'quality'/cell['output_id']/name,cfg,workers=3)
        results[name]={'killed':result['status']=='persistent_failure','evaluation':result}
    save(base/'quality'/cell['output_id']/'summary.json',{'diagnostic_only':True,'mutants':results,
        'killed':sum(r['killed'] for r in results.values()),'total':len(results)})
    print(cell['output_id'],sum(r['killed'] for r in results.values()),'/',len(results),flush=True)

if __name__=='__main__':
    base=ROOT/'runs/development_v2'
    frozen=json.loads((base/'schedule.json').read_text(encoding='utf-8'))
    tasks={t['task_id']:t for t in frozen['tasks'] if t['task_id'] in frozen['generation_tasks']}
    mutants={key:paths(task) for key,task in tasks.items()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[]
        for cell in frozen['cells']:
            summary=base/'outputs'/cell['output_id']/'evaluation/summary.json'
            if not summary.exists() or json.loads(summary.read_text(encoding='utf-8'))['status']!='stable_proxy_valid': continue
            jobs.append(pool.submit(assess,cell,tasks[cell['task_id']],mutants[cell['task_id']]))
        for job in jobs: job.result()
