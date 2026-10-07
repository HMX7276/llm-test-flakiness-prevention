"""Original target tests vs the existing diagnostic mutants; no formal score."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.prepare import save
from runner.development_quality import prepare
from runner.rule_validation_v2 import paths

RUN = ROOT / 'runs/upstream_baseline_v3'
SPECS = {
    'penman': ('penman.graph', 'penman/graph.py', 'tests', ['tests']),
    'Tale': ('tale.pubsub', 'tale/pubsub.py', 'tests', ['tests/test_pubsub.py']),
    'lithoxyl': ('lithoxyl.moment', 'lithoxyl/moment.py', 'lithoxyl/tests',
                ['lithoxyl/tests/test_stats.py::test_momentacc_basic', 'lithoxyl/tests/test_stats.py::test_momentacc_norm']),
    'RandomFileTree': ('randomfiletree.core', 'randomfiletree/core.py', 'randomfiletree/test',
                       ['randomfiletree/test/test_core.py::TestHelperFunctions']),
    'fishbase': ('fishbase.fish_random', 'fishbase/fish_random.py', 'test',
                 ['test/test_random.py::TestFishRandom::test_gen_random_str_01',
                  'test/test_random.py::TestFishRandom::test_gen_string_by_range_02']),
}


def execute(task, variant, mutant, seed, collect=False):
    name = task['project_id']
    module, filename, full, targets = SPECS[name]
    dest = RUN / name / ('full_collection' if collect else variant) / f'run_{seed:03d}'
    record_file = dest / 'execution.json'
    if record_file.exists():
        return json.loads(record_file.read_text(encoding='utf-8'))
    project = dest / 'project'
    dest.mkdir(parents=True, exist_ok=True)
    if not project.exists():
        shutil.copytree(ROOT / task['project_path'], project, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '.git'))
        if mutant:
            shutil.copyfile(mutant / filename, project / filename)
    expected = hashlib.sha256((project / filename).read_bytes()).hexdigest()
    assert expected == hashlib.sha256(((mutant or (ROOT / task['project_path'])) / filename).read_bytes()).hexdigest()
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
    env.update(PYTHONPATH=os.pathsep.join([str(project), str(ROOT / 'runner')]),
               PYTHONHASHSEED=str(seed), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
               PYTHONIOENCODING='utf-8', TEMP=str(dest), TMP=str(dest),
               BASELINE_MODULE=module, BASELINE_ORIGIN_FILE=str(dest / 'origin.json'))
    selections = [full] if collect else targets
    cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-p', 'baseline_origin_plugin',
           '--import-mode=importlib', '-o', 'addopts=', '--junitxml=' + str(dest / 'junit.xml')]
    cmd += [str(project / item) for item in selections]
    if collect:
        cmd.append('--collect-only')
    result = {'project_id': name, 'variant': variant, 'seed': seed, 'commit': task['commit'],
              'scope': 'full_collection_only' if collect else ('full_tests_directory' if name == 'penman' else 'target_test_subset'),
              'selection': selections, 'command': cmd, 'expected_source_sha256': expected}
    try:
        p = subprocess.run(cmd, cwd=dest, env=env, capture_output=True, timeout=50)
        (dest / 'stdout.txt').write_bytes(p.stdout)
        (dest / 'stderr.txt').write_bytes(p.stderr)
        result['return_code'] = p.returncode
    except subprocess.TimeoutExpired as e:
        (dest / 'stdout.txt').write_bytes(e.stdout or b'')
        (dest / 'stderr.txt').write_bytes(e.stderr or b'')
        result.update(status='timeout', cases={})
        save(record_file, result)
        return result
    cases = {}
    for case in ET.parse(dest / 'junit.xml').findall('.//testcase'):
        key = case.get('classname', '') + '::' + case.get('name', '')
        status = 'error' if case.find('error') is not None else 'fail' if case.find('failure') is not None else 'skip' if case.find('skipped') is not None else 'pass'
        cases[key] = status
    origin = json.loads((dest / 'origin.json').read_text(encoding='utf-8'))
    verified = origin['path'] == str((project / filename).resolve()) and origin['sha256'] == expected
    result.update(cases=cases, counts=dict(Counter(cases.values())), origin=origin, origin_verified=verified)
    result['status'] = ('collection_ok' if p.returncode == 0 else 'collection_blocked') if collect else (
        'origin_unverified' if not verified else 'collection_or_setup_error' if 'error' in cases.values()
        else 'fail' if 'fail' in cases.values() else 'pass' if p.returncode == 0 and cases else 'infrastructure_error')
    save(record_file, result)
    return result


def one(task):
    name = task['project_id']
    mutants = prepare(task) if name in ('penman', 'Tale', 'lithoxyl') else paths(task)
    collection = execute(task, 'original', None, 0, collect=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        originals = list(pool.map(lambda seed: execute(task, 'original', None, seed), range(3)))
    stable_pass = set.intersection(*[{k for k, v in r['cases'].items() if v == 'pass'} for r in originals])
    valid_original = all(r.get('origin_verified') and r['status'] in ('pass', 'fail') for r in originals)
    comparisons = {}
    for variant, mutant in mutants.items():
        with ThreadPoolExecutor(max_workers=3) as pool:
            runs = list(pool.map(lambda seed: execute(task, variant, mutant, seed), range(3)))
        valid = valid_original and all(r.get('origin_verified') and r['status'] in ('pass', 'fail') for r in runs)
        newly_failing = sorted(stable_pass.intersection(*[{k for k, v in r['cases'].items() if v == 'fail'} for r in runs])) if valid else []
        comparisons[variant] = {'valid_comparison': valid, 'detected_by_same_original_node_all_three': bool(newly_failing),
                                'newly_failing_nodes': newly_failing, 'runs': runs}
    report = {'project_id': name, 'task_id': task['task_id'], 'commit': task['commit'], 'collection': collection,
              'originals': originals, 'stable_original_passing_nodes': sorted(stable_pass), 'mutants': comparisons,
              'scope': originals[0]['scope'], 'diagnostic_only': True,
              'limitations': ['Three process replicates, not independent tasks.', 'Hand-seeded mutants chosen during development.',
                              'Subset baselines do not establish incremental value over the whole project suite.']}
    save(RUN / name / 'summary.json', report)
    print(name, [r['status'] for r in originals], {k: v['detected_by_same_original_node_all_three'] for k, v in comparisons.items()}, flush=True)
    return report


if __name__ == '__main__':
    tasks = json.loads((ROOT / 'runs/development_v2/schedule.json').read_text(encoding='utf-8'))['tasks']
    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(one, tasks))
    save(RUN / 'summary.json', {'projects': reports, 'protocol_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
