"""Fresh, unperturbed executions of three disputed original tests; primary unchanged."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.development_v1 import config
from runner.evaluate import run_one


if __name__=='__main__':
    mapping=json.loads((ROOT/'review/semantic_v2/mapping_private.json').read_text(encoding='utf-8'))
    schedule=json.loads((ROOT/'runs/development_v2/schedule.json').read_text(encoding='utf-8'))
    cells={c['output_id']:c for c in schedule['cells']}
    tasks={t['task_id']:t for t in schedule['tasks']}
    dest=ROOT/'runs/semantic_review_v2_followup/fresh_unperturbed'
    rows=[]
    for item in mapping:
        if item['review_id'] not in ('S010','S018','S028'):continue
        source=ROOT/item['code_path']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==item['code_sha256']
        cfg={**config(tasks[cells[item['private_output']]['task_id']]),'perturbation':'none'}
        runs=[]
        for seed in range(3):
            folder=dest/item['review_id']/f'run_{seed:03d}'
            record=folder/'evidence.json'
            if record.exists(): r=json.loads(record.read_text(encoding='utf-8'))
            else:
                r=run_one(source,folder,seed,cfg)
                save(record,r)
            assert r['artifact_hash']==item['code_sha256']
            runs.append(r)
        rows.append({'review_id':item['review_id'],'output_id':item['private_output'],
                     'code_sha256':item['code_sha256'],'counts':dict(Counter(r['status'] for r in runs)),'runs':runs})
        print(item['review_id'],rows[-1]['counts'],flush=True)
    save(dest/'summary.json',{'purpose':'Resolve factual disagreement about original code in a clean single run.',
         'execution':'Each replicate is a new Python process and directory; no scheduler or RNG perturbation plugin action.',
         'reviewer_type':'assistant','primary_unchanged':True,'rows':rows})
