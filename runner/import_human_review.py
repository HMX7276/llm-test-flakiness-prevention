"""Validate a user-returned export without conflating AI and human labels."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

def validate(payload,mapping,expected_schema='semantic-review-v1'):
    if payload.get('schema')!=expected_schema or payload.get('reviewer_type')!='human':
        raise ValueError('Wrong schema or reviewer type')
    if not isinstance(payload.get('reviewer'),str) or not payload['reviewer'].strip():
        raise ValueError('Reviewer name/code required')
    expected={row['review_id']:row['code_sha256'] for row in mapping}
    seen=set(); completed=[]; partial=[]
    options={'correctness':{'correct','incorrect','uncertain'},'robustness':{'robust','fragile','uncertain'},
             'adequacy':{'meaningful','weak_or_masked','uncertain'}}
    for row in payload.get('items',[]):
        rid=row.get('review_id')
        if rid not in expected or rid in seen: raise ValueError('Unknown/duplicate review ID')
        seen.add(rid)
        if row.get('code_sha256')!=expected[rid]: raise ValueError('Code hash mismatch: '+rid)
        for field,values in options.items():
            if row.get(field,'') not in values|{''}: raise ValueError('Invalid label: '+field)
        if all(row.get(f) in values for f,values in options.items()) and isinstance(row.get('reason'),str) and row['reason'].strip():
            completed.append(row)
        else: partial.append(row)
    return {'completed':completed,'partial':partial,'not_returned':sorted(set(expected)-seen),
            'reviewer':payload['reviewer'],'reviewer_type':'human','agreement_coefficient':None,
            'agreement_note':'One human reviewer plus assistant annotations; no inter-human agreement claim.'}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('file',type=Path)
    p.add_argument('--packet',choices=['semantic_v1','semantic_v2','semantic_lean_v1'],default='semantic_v1')
    args=p.parse_args()
    raw=args.file.read_bytes()
    packet=ROOT/'review'/args.packet
    mapping=json.loads((packet/'mapping_private.json').read_text(encoding='utf-8'))
    payload=json.loads(raw.decode('utf-8-sig'))
    result=validate(payload,mapping,expected_schema=args.packet.replace('_','-').replace('semantic-','semantic-review-'))
    result.update(imported_utc=datetime.now(timezone.utc).isoformat(),source_sha256=hashlib.sha256(raw).hexdigest())
    dest=packet/'accepted'/(result['source_sha256']+'.json')
    if dest.exists(): raise SystemExit('This export is already imported')
    save(dest,result)
    print('Completed',len(result['completed']),'partial',len(result['partial']),'not returned',len(result['not_returned']))
