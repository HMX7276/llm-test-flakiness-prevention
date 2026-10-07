"""Fixed tiny-corpus cache equivalence probe, distinct from the historical test."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.candidate_reproduce import execute
from runner.prepare import save
from runner.prepare_dev_v1 import extract

RISK='''import numpy as np
from compare_mt import sign_utils
from compare_mt.scorers import BleuScorer

def test_cached_bootstrap_equivalence():
    ref = [['a'], ['b'], ['c'], ['d']]
    outs = [[['a'], ['x'], ['c'], ['x']], [['x'], ['b'], ['x'], ['d']]]
    scorer = BleuScorer(weights=(1.0,))
    cache = [scorer.cache_stats(ref, out) for out in outs]
    cached = sign_utils.eval_with_paired_bootstrap(ref, outs, scorer, num_samples=5, cache_stats=cache)
    direct = sign_utils.eval_with_paired_bootstrap(ref, outs, scorer, num_samples=5)
    assert cached[0] == direct[0]
    assert cached[1] == direct[1]
'''
CLEAN=RISK.replace('from compare_mt import sign_utils', 'from types import SimpleNamespace\nfrom compare_mt import sign_utils').replace(
    'def test_cached_bootstrap_equivalence():',
    '''def test_cached_bootstrap_equivalence(monkeypatch):
    rng = np.random.RandomState()
    initial_state = np.random.get_state()
    rng.set_state(initial_state)
    monkeypatch.setattr(sign_utils, 'np', SimpleNamespace(random=rng, mean=np.mean, median=np.median))''').replace(
    '    direct = sign_utils', '    rng.set_state(initial_state)\n    direct = sign_utils')


def main():
    folder=ROOT/'data/candidate_tasks_v3/compare_mt_bootstrap_cache_001'
    folder.mkdir(parents=True,exist_ok=True)
    c=json.loads((ROOT/'data/sources/compare-mt_provenance.json').read_text(encoding='utf-8'))
    c.update(environment_profile='local_scientific_cache_v1')
    source=ROOT/c['project_path']/'compare_mt/sign_utils.py'
    task={'task_id':folder.name,'project_id':'compare-mt','commit':c['commit'],'project_path':c['project_path'],
          'target':'compare_mt.sign_utils.eval_with_paired_bootstrap',
          'target_source':extract(source,'eval_with_paired_bootstrap'),
          'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
          'provenance':'Constructed tiny-corpus/cache-path adaptation inspired by original test_score_cache_bootstrap; original historical node passed 30/30 in this environment.',
          'dataset_layer':'historical_inspired_constructed','human_review_status':'pending',
          'method_support':'M v2 abstains: NumPy paired state replay is not the stdlib seeded-regression rule.',
          'contract':'Given identical bootstrap draws, explicit-cache and internally computed-cache paths must agree on results. Independent draws need not yield identical results. Do not replace scorer or target function.',
          'limitation':'Known independent win-counting if/else issue in source is not evaluated by cache equivalence; no correctness claim for all statistical output.',
          'entry_seeds':list(range(30)),'sample_count':5,'fixed_before_outcomes':True,
          'clean_status':'Manual candidate reference, not automatic transformation or human-approved equivalence.'}
    if (folder/'task.json').exists():
        assert json.loads((folder/'task.json').read_text(encoding='utf-8'))==task
    else: save(folder/'task.json',task)
    def assertions(code): return [ast.dump(n) for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Assert)]
    assert assertions(RISK)==assertions(CLEAN)
    outcomes={}
    for variant,code in [('risk',RISK),('manual_clean',CLEAN)]:
        test=folder/(variant+'.py')
        if test.exists(): assert test.read_text(encoding='utf-8')==code
        else: test.write_text(code,encoding='utf-8')
        candidate={**c,'test':str(test),'evidence_root':'runs/compare_mt_pair_probe_v3/'+variant}
        with ThreadPoolExecutor(max_workers=3) as pool:
            runs=list(pool.map(lambda seed:execute(candidate,'numpy_entry_state_v3',seed),range(30)))
        outcomes[variant]={'counts':dict(Counter(r['status'] for r in runs)),'runs':runs,
                           'code_sha256':hashlib.sha256(test.read_bytes()).hexdigest()}
        print(variant,outcomes[variant]['counts'],flush=True)
    save(ROOT/'runs/compare_mt_pair_probe_v3/summary.json',{'task':task,'outcomes':outcomes,'assertion_ast_preserved':True})


if __name__=='__main__': main()
