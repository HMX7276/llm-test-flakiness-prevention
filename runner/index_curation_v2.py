import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

if __name__=='__main__':
    decisions={
      'fishbase':('not_reproduced','Actual original test is under test/; dataset omitted that directory. 30/30 pass after explicit dependency installation. Newly added RNG target is a constructed context on another function, not this historical test.'),
      'freezegun':('confirmed_shared_module_state_out_of_scope','30 isolated passes; explicit wrapper first call completes and second fails in all 30 processes. Retained tests.another_module package attribute survives sys.modules deletion; missing module cannot be repatched during subsequent freeze. Duplicate-node probe actually collected one test and is invalid as repeat evidence.'),
      'tangle':('not_reproduced','30/30 isolated pass; EventRegister shared state is a possible lead, not experimentally confirmed flaky.'),
      'nxviz':('environment_blocked','Source inspected; collection failed for missing numpy. Broad Hypothesis float domain/filter is a lead only. Not counted as a reproduced assertion failure.')}
    records=[]
    for name,(status,reason) in decisions.items():
        source=json.loads((ROOT/'data/sources'/f'{name}_provenance.json').read_text(encoding='utf-8'))
        evidence=[]
        for p in (ROOT/'runs/curation_v2'/name).glob('*/summary.json'):
            r=json.loads(p.read_text(encoding='utf-8'))
            evidence.append({'mode':p.parent.name,'counts':r['counts'],'path':str(p.relative_to(ROOT)),
               'valid_for_claim':p.parent.name!='repeat_same_process'})
        records.append({**source,'verified_status':status,'reason':reason,'evidence':evidence,
                        'formal_eligible':False,'human_review_status':'pending'})
    save(ROOT/'data/curation_v2.json',{'records':records,'scope':'Four additional historical leads, not four new eligible targets'})
    print('Indexed 4 leads with exclusions and invalid duplicate-node probe explicitly marked')
