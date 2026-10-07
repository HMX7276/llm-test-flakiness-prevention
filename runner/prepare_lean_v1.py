"""Offline rehearsal of the reduced design; never invokes an API or runs tests.

This artifact uses three already-seen development targets. It is not the frozen
evaluation set. It checks prompt comparability before adding any unseen targets.
"""
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from methods.prevent_v2 import transform
from runner.prompting import build_prompt
from runner.rule_review_status import TASKS, status

DEST = ROOT / 'runs/lean_preparation_v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def main():
    human = status()
    assert human['status'] == 'complete'
    assert all(r['verdict'] == 'preserved' for r in human['completed'].values())
    config = read('configs/models_v1.json')
    warning = (ROOT / 'prompts/warning.txt').read_text(encoding='utf-8')
    assert warning.strip(), 'An empty warning would duplicate B0.'
    tasks = [read(f'data/development_v2/{task}/task.json') for task in TASKS]
    cells, audits = [], []
    for task in tasks:
        tid = task['task_id']
        transformed, evidence = transform(task['target_source'], task['risk_example'], task)
        assert evidence['changed'] and evidence['assertions_ast_preserved']
        # Connect the prompt intervention to the actual human-reviewed control.
        bound = ROOT / 'data/development_v2' / tid / 'transformed.py'
        assert ast.dump(ast.parse(transformed)) == ast.dump(ast.parse(bound.read_text(encoding='utf-8')))
        prompts = {method: build_prompt(task, 'risk', method, warning, transform)
                   for method in ['B0', 'B1', 'B2', 'M']}
        prefix, original_example = prompts['B0'][0].rsplit('Example:\n', 1)
        assert original_example == task['risk_example']
        for method in ['B2', 'M']:
            assert prompts[method][0].rsplit('Example:\n', 1)[0] == prefix
        assert prompts['B1'][0].rsplit('Example:\n', 1)[0] == prefix + warning + '\n'
        assert prompts['B1'][0].rsplit('Example:\n', 1)[1] == original_example
        assert prompts['B2'][0].rsplit('Example:\n', 1)[1] == '[Example omitted]'
        assert prompts['M'][0].rsplit('Example:\n', 1)[1] == transformed
        assert len({p[0] for p in prompts.values()}) == 4
        for prompt, _ in prompts.values():
            assert task['target'] in prompt and task['target_module'] in prompt
        for model in config['models']:
            for method, (prompt, change) in prompts.items():
                for repeat in range(1, 4):
                    cells.append({'task_id': tid, 'model_id': model, 'context': 'risk',
                                  'method': method, 'generation_round': repeat,
                                  'prompt': prompt, 'prompt_sha256': sha(prompt.encode('utf-8')),
                                  'transformation': change})
        audits.append({'task_id': tid, 'project_id': task['project_id'], 'is_heldout': False,
                       'common_public_information_preserved': True,
                       'four_distinct_prompts': True,
                       'transformation_matches_human_reviewed_control': True})
    random.Random(20261005).shuffle(cells)
    for i, cell in enumerate(cells, 1):
        cell['output_id'] = f'lp{i:03d}'
    groups = defaultdict(list)
    for cell in cells:
        groups[(cell['model_id'], cell['method'])].append(cell['output_id'])
    reviewer_rng = random.Random(20261006)
    reviewed = []
    for group in sorted(groups):
        reviewed.extend(reviewer_rng.sample(sorted(groups[group]), 6))
    assert len(cells) == 72 and len(set(reviewed)) == 48
    assert len({(c['task_id'], c['model_id'], c['method'], c['generation_round']) for c in cells}) == 72
    assert set(Counter((c['task_id'], c['model_id'], c['method']) for c in cells).values()) == {3}
    sources = ['methods/prevent_v1.py', 'methods/prevent_v2.py', 'runner/prompting.py',
               'configs/models_v1.json', 'prompts/warning.txt']
    sources += [f'data/development_v2/{tid}/task.json' for tid in TASKS]
    result = {
        'schema': 'lean-preparation-v1', 'status': 'preparation_only_not_frozen',
        'formal_dataset': False, 'api_calls_made': 0,
        'scope': 'Offline design rehearsal on already-seen development targets; not an independent evaluation.',
        'tasks': tasks, 'config': config, 'cells': cells,
        'execution_seeds': list(range(30)), 'human_rule_review': human,
        'audit': audits,
        'human_sampling_draft': {'output_ids': sorted(reviewed),
                                'rule': '6 scheduled cells per model/method stratum, sampled before any API outcomes; missing outputs stay missing, no success-based replacements.',
                                'scope': '48 sampled judgments only; cannot claim all 72 artifacts human-validated. Regenerate before freeze if task set changes.'},
        'source_sha256': {p: sha((ROOT / p).read_bytes()) for p in sources},
        'freeze_requirements': ['Finalize task inclusion/exclusion and development/held-out classification.',
                                'Lock mutation catalog, adequacy rubric, execution gates, outcome denominators, and statistical analysis.',
                                'Revalidate source/prompt/adapter hashes and configuration before dispatch.',
                                'A separate runner must refuse this preparation_only status.'],
    }
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    DEST.mkdir(parents=True, exist_ok=True)
    schedule = DEST / 'schedule_draft.json'
    if schedule.exists() and schedule.read_bytes() != encoded:
        raise SystemExit('Preparation contents changed. Preserve this artifact and create a new version.')
    schedule.write_bytes(encoded)
    print(f'Offline checks passed: {len(tasks)} seen tasks, 72 schedule cells, 4 comparable prompts per task, 48 preselected review cells. API calls: 0.')


if __name__ == '__main__':
    main()
