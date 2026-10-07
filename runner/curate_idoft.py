"""Deterministic triage only. Dataset categories are leads, not verified labels."""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

PRIORITY_PROJECTS=[
    'goodmami/penman','stfc/fparser','pythological/kanren','mojochao/configaro',
    'mahmoud/lithoxyl','chinapnr/fishbase','ericmjl/nxviz','klieret/RandomFileTree',
    'grabbles/grabbit','kevinarpe/kevinarpe-rambutan3','fifman/tangle',
    'spulec/freezegun','irmen/Tale','jerodg/jgutils','neulab/compare-mt']


if __name__=='__main__':
    path=ROOT/'data/idoft_py_data.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig',newline='')))
    key=next(k for k in rows[0] if k.startswith('Pytest Test Name'))
    candidates=[]
    for row in rows:
        if row['Category'] not in ['NOD','ID']:
            continue
        project=row['Project URL'].removeprefix('https://github.com/')
        candidates.append({'project':project,'commit':row['SHA Detected'],'test':row[key],
                           'reported_category':row['Category'],'reported_status':row['Status'],
                           'fix_pr':row['PR Link'],'notes':row['Notes'],
                           'verified_risk':None,'eligibility':'not_yet_verified',
                           'priority':PRIORITY_PROJECTS.index(project) if project in PRIORITY_PROJECTS else 999})
    ordered=sorted(candidates,key=lambda r:(r['priority'],r['project'],r['test'],r['commit']))
    seen=set(); project_counts={}; shortlist=[]
    for c in ordered:
        identity=(c['project'],c['test'])
        if identity in seen or project_counts.get(c['project'],0)>=2:
            continue
        seen.add(identity);project_counts[c['project']]=project_counts.get(c['project'],0)+1
        shortlist.append(c)
        if len(shortlist)==20:
            break
    result={'source':'https://github.com/TestingResearchIllinois/idoft/blob/main/py-data.csv',
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'selection_stage':'development_source_triage_only','category_filter':['NOD','ID'],
            'rule':'Prefer plausible locally runnable non-service projects; at most two distinct tests per project; deduplicate test versions. Priority is a declared manual triage list, not a random sample.',
            'total_source_rows':len(rows),'category_candidates':len(candidates),
            'shortlist_count':len(shortlist),'shortlist_projects':len(set(c['project'] for c in shortlist)),
            'shortlist':shortlist,'candidate_records':candidates}
    save(ROOT/'data/candidate_pool.json',result)
    print('Source rows',len(rows),'NOD/ID candidates',len(candidates),'shortlist',len(shortlist),'projects',result['shortlist_projects'])
