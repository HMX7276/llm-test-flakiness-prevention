"""Reproducible initial and scientific-cache profiles for candidate batch 3."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.candidate_reproduce import execute
from runner.prepare import save


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('project', choices=['kevinarpe-rambutan3','grabbit','compare-mt'])
    parser.add_argument('--scientific-cache', action='store_true')
    parser.add_argument('--include-node', action='store_true')
    args=parser.parse_args()
    c=json.loads((ROOT/'data/sources'/(args.project+'_provenance.json')).read_text(encoding='utf-8'))
    c['evidence_root']='runs/curation_v3_initial'
    if args.scientific_cache:
        c.update(evidence_root='runs/curation_v3_scientific',environment_profile='local_scientific_cache_v1')
    if args.include_node:
        assert args.project=='grabbit'
        c.update(evidence_root='runs/curation_v3_grabbit_include',test='grabbit/tests/test_core.py::TestLayout::test_init_with_include_arg[local]')
    first=execute(c,'isolated_clean_options',0)
    print('first',first['status'],flush=True)
    runs=[first]
    if first['status'] in ('pass','fail'):
        with ThreadPoolExecutor(max_workers=3) as pool:
            runs+=list(pool.map(lambda seed:execute(c,'isolated_clean_options',seed),range(1,30)))
    summary={'candidate':c,'runs':runs,'counts':dict(Counter(r['status'] for r in runs))}
    save(ROOT/c['evidence_root']/args.project/'summary.json',summary)
    print(summary['counts'],flush=True)
