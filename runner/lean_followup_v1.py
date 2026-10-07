"""Frozen follow-up on seen development tasks; offline freeze, API, and execution."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.prepare import save
from runner.evaluate import evaluate
from runner.rule_validation_v2 import paths
from runner.rule_review_status import status
import runner.development_v1 as engine

RUN = ROOT / 'runs/lean_followup_v1'
engine.RUN = RUN
SOURCES = ['runner/lean_followup_v1.py', 'runner/development_v1.py', 'runner/evaluate.py',
           'runner/trace_plugin.py', 'runner/api_client.py', 'runner/prepare.py',
           'analysis/format_sensitivity.py', 'methods/prevent_v1.py', 'methods/prevent_v2.py',
           'runner/prompting.py', 'configs/models_v1.json', 'prompts/warning.txt',
           'notes/lean_followup_v1_protocol.txt', 'configs/requirements-dev-v2.lock.txt']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def snapshot(source, dest):
    if dest.exists():
        raise RuntimeError(f'Snapshot destination already exists: {dest.relative_to(ROOT)}')
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))


def freeze():
    if RUN.exists():
        raise SystemExit('Refusing to overwrite frozen run or a partial freeze; inspect before a new version.')
    draft = load(ROOT / 'runs/lean_preparation_v1/schedule_draft.json')
    assert draft['status'] == 'preparation_only_not_frozen' and len(draft['cells']) == 72
    human = status()
    assert human['status'] == 'complete' and all(v['verdict'] == 'preserved' for v in human['completed'].values())
    for name, expected in draft['source_sha256'].items():
        assert digest(ROOT / name) == expected, name
    tasks, defects = [], {}
    # Verify all expected source identities before creating any new evidence.
    for task in draft['tasks']:
        source = ROOT / task['project_path'] / (task['target_module'].replace('.', '/') + '.py')
        assert digest(source) == task['source_sha256'], task['task_id']
    for task in draft['tasks']:
        t = dict(task)
        tid = t['task_id']
        package = t['target_module'].split('.')[0]
        original = ROOT / t['project_path']
        dest = RUN / 'projects' / tid
        snapshot(original / package, dest / package)
        t['upstream_project_path'] = t['project_path']
        t['project_path'] = dest.relative_to(ROOT).as_posix()
        t['frozen_batch_role'] = 'previously_seen_development_target'
        tasks.append(t)
        defects[tid] = {}
        for name, origin in sorted(paths(task).items()):
            mdest = RUN / 'mutants' / tid / name
            snapshot(origin / package, mdest / package)
            metadata = load(origin / 'mutation.json')
            save(mdest / 'mutation.json', metadata)
            defects[tid][name] = {'project_path': mdest.relative_to(ROOT).as_posix(),
                                   'mutation': metadata, 'source_origin': origin.relative_to(ROOT).as_posix()}
    frozen = {**draft, 'schema': 'lean-followup-v1', 'status': 'frozen_seen_task_followup',
              'scope': 'Prospective repeated generations on three already-seen development targets; not a held-out evaluation.',
              'tasks': tasks, 'mutants': defects, 'human_rule_review': human,
              'protocol': 'notes/lean_followup_v1_protocol.txt',
              'source_sha256': {p: digest(ROOT / p) for p in SOURCES},
              'python_version': sys.version, 'executable': sys.executable,
              'formal_dataset': False}
    frozen.pop('freeze_requirements', None)
    frozen['human_sampling_draft']['status'] = 'frozen_before_generation'
    files = sorted(p for folder in ['projects', 'mutants'] for p in (RUN / folder).rglob('*') if p.is_file())
    frozen['snapshot_sha256'] = {p.relative_to(ROOT).as_posix(): digest(p) for p in files}
    save(RUN / 'schedule.json', frozen)
    (RUN / 'schedule.sha256').write_text(digest(RUN / 'schedule.json') + '\n', encoding='ascii')
    print(f'Frozen 72 planned generations, 3 seen tasks, 7 diagnostic defects; {len(files)} snapshot files.', flush=True)


def verified():
    assert digest(RUN / 'schedule.json') == (RUN / 'schedule.sha256').read_text().strip()
    frozen = load(RUN / 'schedule.json')
    assert frozen['status'] == 'frozen_seen_task_followup'
    for bucket in ['source_sha256', 'snapshot_sha256']:
        for p, expected in frozen[bucket].items():
            assert digest(ROOT / p) == expected, f'Frozen dependency changed: {p}'
    return frozen


def evaluate_one(cell, tasks):
    dest = RUN / 'outputs' / cell['output_id']
    record_path = dest / 'record.json'
    if not record_path.exists() or load(record_path)['status'] != 'api_success':
        return
    result = evaluate(dest / 'test_generated.py', dest / 'evaluation', engine.config(tasks[cell['task_id']]), workers=3)
    print(cell['output_id'], result['status'], result['counts'], flush=True)


def quality_one(cell, tasks, mutants):
    out = RUN / 'outputs' / cell['output_id']
    summary = out / 'evaluation/summary.json'
    if not summary.exists() or load(summary)['status'] != 'stable_proxy_valid':
        return
    task = tasks[cell['task_id']]
    results = {}
    for name, definition in mutants[cell['task_id']].items():
        cfg = {**engine.config(task), 'project_path': str(ROOT / definition['project_path']), 'hash_seeds': [0, 1, 2]}
        dest = RUN / 'quality' / cell['output_id'] / name
        result = evaluate(out / 'test_generated.py', dest, cfg, workers=3)
        executions = load(dest / 'executions.json') if (dest / 'executions.json').exists() else []
        hits = [r['status'] == 'fail' and r.get('target_calls', 0) > 0 for r in executions]
        results[name] = {'stable_detection': len(hits) == 3 and all(hits),
                         'any_detection': any(hits), 'evaluation': result}
    stable = sum(r['stable_detection'] for r in results.values())
    save(RUN / 'quality' / cell['output_id'] / 'summary.json',
         {'diagnostic_only': True, 'mutants': results, 'stable_detected': stable, 'total': len(results)})
    print('quality', cell['output_id'], stable, '/', len(results), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['freeze', 'verify', 'generate', 'evaluate', 'quality'])
    parser.add_argument('--limit', type=int, default=72)
    args = parser.parse_args()
    if args.phase == 'freeze':
        freeze()
        return
    frozen = verified()
    if args.phase == 'verify':
        print('Frozen schedule, code, and project/defect snapshot hashes verified. No API calls.')
        return
    tasks = {t['task_id']: t for t in frozen['tasks']}
    cells = frozen['cells'][:max(0, min(args.limit, 72))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        if args.phase == 'generate':
            jobs = [pool.submit(engine.generate, c, frozen['config']) for c in cells]
        elif args.phase == 'evaluate':
            jobs = [pool.submit(evaluate_one, c, tasks) for c in cells]
        else:
            jobs = [pool.submit(quality_one, c, tasks, frozen['mutants']) for c in cells]
        for job in jobs:
            job.result()


if __name__ == '__main__':
    main()
