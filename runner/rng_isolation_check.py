"""Real-package checks: seeded dependency patch must restore module and global RNG."""
import json
from pathlib import Path
import random
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

if __name__=='__main__':
    schedule=json.loads((ROOT/'runs/development_v2/schedule.json').read_text(encoding='utf-8'))
    results=[]
    for task in schedule['tasks']:
        if task['project_id'] not in ['RandomFileTree','fishbase']: continue
        sys.path.insert(0,str(ROOT/task['project_path']))
        import importlib
        module=importlib.import_module(task['target_module'])
        code=(ROOT/'data/development_v2'/task['task_id']/'transformed.py').read_text(encoding='utf-8')
        namespace={}
        exec(compile(code,'<reviewed_rule_output>','exec'),namespace)
        original=module.random
        checks=[]
        for seed in [0,1,123456]:
            random.seed(seed); before=random.getstate()
            with pytest.MonkeyPatch.context() as mp:
                namespace['test_example'](mp)
            checks.append({'entry_seed':seed,'module_restored':module.random is original,
                           'global_rng_unchanged':random.getstate()==before})
        assert all(c['module_restored'] and c['global_rng_unchanged'] for c in checks)
        results.append({'task_id':task['task_id'],'checks':checks})
    save(ROOT/'runs/rule_validation_v2/rng_isolation.json',results)
    print('Both real-package RNG seams restored; global RNG unchanged for all 6 checks')
