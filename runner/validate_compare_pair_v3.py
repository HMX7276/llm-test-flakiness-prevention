"""Check restoration and two cache-path defects of the manual candidate pair."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.candidate_reproduce import execute
from runner.prepare import save


def main():
    folder=ROOT/'data/candidate_tasks_v3/compare_mt_bootstrap_cache_001'
    provenance=json.loads((ROOT/'data/sources/compare-mt_provenance.json').read_text(encoding='utf-8'))
    run=ROOT/'runs/compare_mt_pair_validation_v3'
    wrapper=run/'test_isolation.py'
    run.mkdir(parents=True,exist_ok=True)
    # Embed the unchanged reviewed candidate function so pytest import modes do not change its dependencies.
    code=(folder/'manual_clean.py').read_text(encoding='utf-8').replace('def test_cached_bootstrap_equivalence(', 'def _case(')
    code+='''
from pytest import MonkeyPatch

def test_restores_rng_and_dependency():
    original_dependency = sign_utils.np
    before = np.random.get_state()
    with MonkeyPatch.context() as patch:
        _case(patch)
    after = np.random.get_state()
    assert sign_utils.np is original_dependency
    assert before[0] == after[0]
    assert np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]
'''
    if wrapper.exists(): assert wrapper.read_text(encoding='utf-8')==code
    else: wrapper.write_text(code,encoding='utf-8')
    variants={'restoration':(Path(provenance['project_path']),wrapper)}
    original=(ROOT/provenance['project_path']/'compare_mt/sign_utils.py').read_text(encoding='utf-8')
    old='    cache_stats = [scorer.cache_stats(ref, out) for out in outs]'
    assert original.count(old)==1
    for name,wrong in [('reverse_explicit_cache','list(reversed(cache_stats))'),('duplicate_first_cache','[cache_stats[0] for _ in outs]')]:
        dest=run/'mutants'/name
        if not dest.exists():
            shutil.copytree(ROOT/provenance['project_path']/'compare_mt',dest/'compare_mt',ignore=shutil.ignore_patterns('__pycache__'))
        changed=original.replace(old,old+'\n  else:\n    cache_stats = '+wrong)
        (dest/'compare_mt/sign_utils.py').write_text(changed,encoding='utf-8')
        save(dest/'mutation.json',{'original_commit':provenance['commit'],'source_file':'compare_mt/sign_utils.py',
                                'before':old,'after':old+'\n  else:\n    cache_stats = '+wrong})
        variants[name]=(dest,folder/'manual_clean.py')
    results={}
    for name,(project,test) in variants.items():
        c={**provenance,'project_path':str(project),'test':str(test),'environment_profile':'local_scientific_cache_v1',
           'evidence_root':'runs/compare_mt_pair_validation_v3/'+name}
        with ThreadPoolExecutor(max_workers=3) as pool:
            runs=list(pool.map(lambda seed:execute(c,'numpy_entry_state_v3',seed),range(3)))
        results[name]={'counts':dict(Counter(r['status'] for r in runs)), 'runs':runs,
                      'source_sha256':hashlib.sha256((ROOT/project/'compare_mt/sign_utils.py').read_bytes()).hexdigest()}
        print(name,results[name]['counts'],flush=True)
    save(run/'summary.json',{'diagnostic_only':True,'reviewer_type':'assistant','human_equivalence_review':'pending',
                            'candidate_test_sha256':hashlib.sha256((folder/'manual_clean.py').read_bytes()).hexdigest(),'results':results})


if __name__=='__main__':main()
