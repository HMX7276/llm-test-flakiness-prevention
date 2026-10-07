import concurrent.futures
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.candidate_reproduce import execute

if __name__=='__main__':
    records=[]
    for name in ['fishbase','freezegun','tangle','nxviz']:
        c=json.loads((ROOT/'data/sources'/f'{name}_provenance.json').read_text(encoding='utf-8'))
        c['evidence_root']='runs/curation_v2'
        if name=='fishbase':
            c['reported_test']=c['test']
            c['test']='test/test_common.py::TestFishCommon::test_yaml_conf_as_dict_01'
        if name=='nxviz': c['test']='tests/test_geometry.py::test_correct_negative_angle'
        modes=['isolated_clean_options','repeat_same_process'] if name=='freezegun' else ['isolated_clean_options']
        for mode in modes:
            n=1 if name=='nxviz' else 30
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                runs=list(pool.map(lambda seed:execute(c,mode,seed),range(n)))
            result={'candidate':c,'mode':mode,'runs':runs,'counts':dict(Counter(r['status'] for r in runs))}
            save(ROOT/c['evidence_root']/name/mode/'summary.json',result)
            records.append(result)
            print(name,mode,result['counts'],flush=True)
        if name=='freezegun':
            # Duplicate node IDs are deduplicated by this pytest version even with
            # --keep-duplicates. Use explicit calls and retain the invalid probe.
            wrapper=ROOT/'runs/curation_v2/freezegun/test_repeat_wrapper.py'
            wrapper.write_text('from tests.test_class_import import test_import_after_start as original\n\ndef test_twice():\n    original()\n    print("first invocation completed")\n    original()\n    print("second invocation completed")\n',encoding='utf-8')
            repeated={**c,'test':str(wrapper)}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                runs=list(pool.map(lambda seed:execute(repeated,'repeat_wrapper',seed),range(30)))
            result={'candidate':repeated,'mode':'repeat_wrapper','runs':runs,'counts':dict(Counter(r['status'] for r in runs)),
                    'prior_probe_invalid':'repeat_same_process passed only one collected instance; not evidence of two invocations.'}
            save(ROOT/c['evidence_root']/name/'repeat_wrapper/summary.json',result)
            records.append(result)
            print(name,'repeat_wrapper',result['counts'],flush=True)
    save(ROOT/'data/curation_v2_raw.json',records)
