"""Build an auditable index from completed evidence, not IDoFT labels alone."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

def main():
    decisions={
      'kanren':('not_reproduced','Keep historical lead, no mixed outcome in 30 isolated runs.'),
      'configaro':('not_reproduced_after_harness_fix','Original pytest options require absent plugins; separate addopts-only override passes 30/30.'),
      'lithoxyl':('controlled_random_state_sensitive_with_faulty_oracle','Entry RNG sweep mixes pass/fail; original signed skewness helper is defective. Original pair excluded pending review; constructed diagnostic stored separately.'),
      'RandomFileTree':('not_reproduced','Both isolated and entry RNG sweep 30/30 pass.'),
      'Tale':('controlled_schedule_sensitive','Unperturbed 30/30 pass; explicit 0/150ms assertion-entry scheduling delay mixes 15/15. Adapted development context only, no natural-rate claim.')}
    records=[]
    for name,(status,decision) in decisions.items():
        source=json.loads((ROOT/'data/sources'/f'{name}_provenance.json').read_text(encoding='utf-8'))
        sourcefile=ROOT/source['project_path']/source['test'].split('::')[0]
        summaries={path.parent.name:{'counts':json.loads(path.read_text(encoding='utf-8'))['counts'],'path':str(path.relative_to(ROOT))}
                   for path in (ROOT/'runs/curation_v1'/name).glob('*/summary.json')}
        records.append({**source,'verified_status':status,'decision':decision,
             'source_test_sha256':hashlib.sha256(sourcefile.read_bytes()).hexdigest(),
             'evidence':summaries,'formal_dataset_eligible':False,'human_review_status':'pending'})
    save(ROOT/'data/curation_v1.json',{'date':'2026-10-05','records':records,
        'ordinary_reproduction':'No new unperturbed pass/fail mixed case confirmed in this five-project batch.'})
    schedule=json.loads((ROOT/'runs/development_v1/schedule.json').read_text(encoding='utf-8'))
    save(ROOT/'data/development_v1/index.json',{'version':'development_v1','distinct_target_count':len(schedule['tasks']),
        'projects':list(dict.fromkeys(t['project_id'] for t in schedule['tasks'])),
        'tasks':[{k:t[k] for k in ['task_id','project_id','target','dataset_layer','eligibility','human_review_status']} for t in schedule['tasks']],
        'formal_eligible':False,'planned_development_target_count':24,
        'reason':'Small diagnostic expansion; human review and stronger method support needed before formal freezing.'})
    print('Indexed 5 verified leads and 3 diagnostic development targets')
if __name__=='__main__': main()
