"""Diagnostic defects for every passing post-hoc reviewed output; no primary edits."""
import concurrent.futures
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.lean_followup_v1 import RUN, verified, load, engine
from runner.evaluate import run_one, classify
from runner.prepare import save


def main():
    frozen = verified()
    tasks = {t['task_id']: t for t in frozen['tasks']}
    source = RUN / 'reviewed_execution/summary.json'
    reviewed = load(source)
    selected = [r for r in reviewed['rows'] if r['outcome']['status'] == 'stable_proxy_valid']
    assert len(selected) == 14
    dest = RUN / 'reviewed_quality'
    manifest = {'post_hoc': True, 'diagnostic_only': True,
                'selection': 'All 14 passing outputs from the full 15-output gate sensitivity analysis.',
                'reviewed_execution_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'schedule_sha256': hashlib.sha256((RUN / 'schedule.json').read_bytes()).hexdigest(),
                'rule': 'Three fresh processes per applicable frozen defect; stable detection requires 3/3 call-phase failures with target calls.',
                'code_sha256': {r['output_id']: r['outcome']['code_sha256'] for r in selected}}
    if (dest / 'manifest.json').exists():
        assert load(dest / 'manifest.json') == manifest
    else:
        save(dest / 'manifest.json', manifest)
    rows = []
    for row in selected:
        oid, tid = row['output_id'], row['task_id']
        src = RUN / 'outputs' / oid / 'test_generated.py'
        assert hashlib.sha256(src.read_bytes()).hexdigest() == manifest['code_sha256'][oid]
        mutants = {}
        for name, definition in frozen['mutants'][tid].items():
            folder = dest / oid / name
            if (folder / 'executions.json').exists():
                executions = load(folder / 'executions.json')
                assert len(executions) == 3 and all(r['artifact_hash'] == manifest['code_sha256'][oid] for r in executions)
            else:
                cfg = {**engine.config(tasks[tid]), 'project_path': str(ROOT / definition['project_path']),
                       'hash_seeds': [0, 1, 2]}
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                    executions = list(pool.map(lambda seed: run_one(src, folder / f'run_{seed:03d}', seed, cfg), range(3)))
                save(folder / 'executions.json', executions)
            evaluation = classify(executions, True)
            evaluation.update(code_sha256=manifest['code_sha256'][oid], post_hoc=True)
            save(folder / 'summary.json', evaluation)
            hits = [r['status'] == 'fail' and r.get('target_calls', 0) > 0 for r in executions]
            mutants[name] = {'stable_detection': len(hits) == 3 and all(hits), 'any_detection': any(hits),
                             'evaluation': evaluation}
        result = {'output_id': oid, 'task_id': tid, 'model_id': row['model_id'], 'method': row['method'],
                  'code_sha256': manifest['code_sha256'][oid], 'mutants': mutants,
                  'stable_detected': sum(m['stable_detection'] for m in mutants.values()),
                  'total': len(mutants), 'post_hoc': True, 'diagnostic_only': True}
        save(dest / oid / 'summary.json', result)
        rows.append(result)
        print(oid, result['stable_detected'], '/', result['total'], flush=True)
    verified()
    summary = {'post_hoc': True, 'diagnostic_only': True, 'primary_unchanged': True,
               'outputs': len(rows), 'outputs_detecting_any': sum(r['stable_detected'] > 0 for r in rows),
               'executions': sum(m['evaluation']['executions'] for r in rows for m in r['mutants'].values()), 'rows': rows}
    save(dest / 'summary.json', summary)
    print('Complete:', summary['outputs'], 'outputs;', summary['executions'], 'executions;',
          summary['outputs_detecting_any'], 'detect at least one diagnostic defect.', flush=True)


if __name__ == '__main__':
    main()
