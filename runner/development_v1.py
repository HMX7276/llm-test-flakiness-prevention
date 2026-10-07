"""Resumable generation/evaluation for the frozen multi-project development set."""
import argparse
import concurrent.futures
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.api_client import complete
from runner.prepare import save
from runner.evaluate import evaluate
from analysis.format_sensitivity import unwrap
RUN=ROOT/'runs/development_v1'

def generate(cell,cfg):
    dest=RUN/'outputs'/cell['output_id']
    if (dest/'record.json').exists(): return
    payload={'model':cell['model_id'],'messages':[{'role':'user','content':cell['prompt']}],
        'temperature':cfg['temperature'],'top_p':cfg['top_p'],'max_tokens':cfg['max_tokens'],
        'stream':False,**cfg['models'][cell['model_id']]}
    save(dest/'request.json',payload)
    started=datetime.now(timezone.utc).isoformat()
    response,attempts=complete(payload,timeout=cfg['request_timeout_seconds'],retries=cfg['max_transport_retries'])
    record={k:v for k,v in cell.items() if k!='prompt'}
    record.update(started_utc=started,attempts=attempts,status='api_success' if response else 'api_incomplete')
    (dest/'prompt.txt').write_text(cell['prompt'],encoding='utf-8')
    if response:
        save(dest/'response.json',response)
        choices=response.get('choices') or [{}]
        content=choices[0].get('message',{}).get('content') or ''
        (dest/'content.txt').write_text(content,encoding='utf-8')
        (dest/'test_generated.py').write_text(unwrap(content),encoding='utf-8')
        record.update(usage=response.get('usage'),returned_model=response.get('model'),
            finish_reason=choices[0].get('finish_reason'),system_fingerprint=response.get('system_fingerprint'),
            code_sha256=hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest())
    save(dest/'record.json',record)
    print(cell['output_id'],cell['model_id'],record['status'],flush=True)

def config(task):
    return {**task,'project_path':str(ROOT/task['project_path']),'hash_seeds':list(range(30)),
            'execution_timeout_seconds':15}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('phase',choices=['generate','controls','evaluate'])
    p.add_argument('--limit',type=int,default=48)
    args=p.parse_args()
    frozen=json.loads((RUN/'schedule.json').read_text(encoding='utf-8'))
    tasks={t['task_id']:t for t in frozen['tasks']}
    if args.phase=='generate':
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda c:generate(c,frozen['config']),frozen['cells'][:args.limit]))
    elif args.phase=='controls':
        for task in tasks.values():
            for condition in ['risk','clean','transformed']:
                test=ROOT/'data/development_v1'/task['task_id']/(condition+'.py')
                result=evaluate(test,RUN/'controls'/task['task_id']/condition,config(task),workers=3)
                print(task['task_id'],condition,result['status'],result['counts'],flush=True)
    else:
        for cell in frozen['cells'][:args.limit]:
            dest=RUN/'outputs'/cell['output_id']
            if not (dest/'record.json').exists(): continue
            record=json.loads((dest/'record.json').read_text(encoding='utf-8'))
            if record['status']!='api_success': continue
            result=evaluate(dest/'test_generated.py',dest/'evaluation',config(tasks[cell['task_id']]),workers=4)
            print(cell['output_id'],result['status'],result['counts'],flush=True)
if __name__=='__main__': main()
