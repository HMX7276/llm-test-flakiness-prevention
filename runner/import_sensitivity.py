"""Post-hoc B2 prompt-metadata sensitivity. No primary result replacement."""
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
from runner.development_v1 import config
from runner.evaluate import evaluate
from analysis.format_sensitivity import unwrap
RUN=ROOT/'runs/development_v1_import_sensitivity'

def freeze():
    if (RUN/'schedule.json').exists(): return
    original=json.loads((ROOT/'runs/development_v1/schedule.json').read_text(encoding='utf-8'))
    tasks={t['task_id']:t for t in original['tasks']}
    cells=[]
    for c in original['cells']:
        if c['method']!='B2': continue
        task=tasks[c['task_id']]
        prompt=c['prompt']+'\nFully qualified target: '+task['target']+'\nImport module: '+task['target_module']+'\n'
        cells.append({**c,'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
    save(RUN/'schedule.json',{'config':original['config'],'tasks':original['tasks'],'cells':cells,
        'purpose':'Post-hoc B2 namespace information diagnostic, not primary method comparison. Two context labels now identical repeat prompts.'})

def generate(cell,cfg):
    dest=RUN/'outputs'/cell['output_id']
    if (dest/'record.json').exists(): return
    payload={'model':cell['model_id'],'messages':[{'role':'user','content':cell['prompt']}],
        'temperature':cfg['temperature'],'top_p':cfg['top_p'],'max_tokens':cfg['max_tokens'],'stream':False,
        **cfg['models'][cell['model_id']]}
    save(dest/'request.json',payload)
    start=datetime.now(timezone.utc).isoformat()
    response,attempts=complete(payload,timeout=90,retries=0)
    record={k:v for k,v in cell.items() if k!='prompt'}
    record.update(started_utc=start,attempts=attempts,status='api_success' if response else 'api_incomplete')
    if response:
        save(dest/'response.json',response)
        content=response['choices'][0]['message'].get('content') or ''
        (dest/'content.txt').write_text(content,encoding='utf-8')
        (dest/'test_generated.py').write_text(unwrap(content),encoding='utf-8')
        record.update(code_sha256=hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest(),usage=response.get('usage'))
    save(dest/'record.json',record)
    print(cell['output_id'],record['status'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('phase',choices=['generate','evaluate'])
    args=p.parse_args()
    freeze()
    schedule=json.loads((RUN/'schedule.json').read_text(encoding='utf-8'))
    if args.phase=='generate':
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda cell:generate(cell,schedule['config']),schedule['cells']))
    else:
        tasks={t['task_id']:t for t in schedule['tasks']}
        for cell in schedule['cells']:
            dest=RUN/'outputs'/cell['output_id']
            if not (dest/'test_generated.py').exists(): continue
            summary=evaluate(dest/'test_generated.py',dest/'evaluation',config(tasks[cell['task_id']]),workers=4)
            print(cell['output_id'],summary['status'],summary['counts'],flush=True)
