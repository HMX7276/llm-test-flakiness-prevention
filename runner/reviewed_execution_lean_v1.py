"""Post-hoc sensitivity analysis of every held output; primary evidence untouched.

Assistant inspection found only local dependency patches / literal pytest import.
This is execution review, not a human semantic decision or a sandbox guarantee.
All 15 held outputs are retained, including the invalid Random context manager.
"""
import ast
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.lean_followup_v1 import RUN, verified, load, engine
from runner.evaluate import run_one, classify
from runner.prepare import save

IDS = ['lp006', 'lp010', 'lp011', 'lp013', 'lp022', 'lp030', 'lp032',
       'lp033', 'lp034', 'lp041', 'lp047', 'lp052', 'lp055', 'lp057', 'lp069']


def main():
    frozen = verified()
    tasks = {t['task_id']: t for t in frozen['tasks']}
    held = [c for c in frozen['cells'] if load(RUN / 'outputs' / c['output_id'] /
            'evaluation/summary.json')['status'] == 'execution_review_required']
    assert sorted(c['output_id'] for c in held) == IDS
    dest = RUN / 'reviewed_execution'
    manifest = {'post_hoc': True, 'reviewer_type': 'assistant',
                'scope': 'All 15 gate-held original outputs; primary classifications unchanged.',
                'inspection': 'Local dependency substitutions only; no file, network or process operations. '
                              'lp011 lacks patch restoration; lp022 misuses Random as a context manager. '
                              'These negative properties are retained, not repaired.',
                'code_sha256': {c['output_id']: load(RUN / 'outputs' / c['output_id'] /
                                                   'record.json')['code_sha256'] for c in held}}
    if (dest / 'manifest.json').exists():
        assert load(dest / 'manifest.json') == manifest
    else:
        save(dest / 'manifest.json', manifest)
    rows = []
    for cell in held:
        oid = cell['output_id']
        src = RUN / 'outputs' / oid / 'test_generated.py'
        sha = hashlib.sha256(src.read_bytes()).hexdigest()
        assert sha == manifest['code_sha256'][oid]
        tree = ast.parse(src.read_text(encoding='utf-8'))
        target = tasks[cell['task_id']]['target_qualname'].split('.')[-1]
        one_test = len([n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]) == 1
        assertion = any(isinstance(n, ast.Assert) and not isinstance(n.test, ast.Constant) for n in ast.walk(tree))
        call = any(isinstance(n, ast.Call) and ((isinstance(n.func, ast.Name) and n.func.id == target) or
                   (isinstance(n.func, ast.Attribute) and n.func.attr == target)) for n in ast.walk(tree))
        proxy = one_test and assertion and call
        assert proxy, oid
        folder = dest / oid
        if (folder / 'summary.json').exists():
            result = load(folder / 'summary.json')
            assert result['code_sha256'] == sha and result['executions'] == 30
        else:
            cfg = engine.config(tasks[cell['task_id']])
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                runs = list(pool.map(lambda seed: run_one(src, folder / f'run_{seed:03d}', seed, cfg), range(30)))
            result = classify(runs, proxy)
            result.update(code_sha256=sha, post_hoc=True, reviewer_type='assistant',
                          purpose='Supplemental original-code execution; primary unchanged.',
                          semantic_review='See separate human reconciliation; not inferred from passing.')
            save(folder / 'executions.json', runs)
            save(folder / 'summary.json', result)
        rows.append({**{k: cell[k] for k in ['output_id', 'task_id', 'model_id', 'method']}, 'outcome': result})
        print(oid, result['status'], result['counts'], flush=True)
    verified()
    save(dest / 'summary.json', {'post_hoc': True, 'reviewer_type': 'assistant', 'rows': rows,
                               'primary_unchanged': True, 'diagnostic_quality_evaluated': False})


if __name__ == '__main__':
    main()
