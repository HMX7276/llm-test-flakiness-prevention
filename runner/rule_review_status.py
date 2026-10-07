"""Read separately returned, hash-bound human judgments of fixed rule examples."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ['tale_topic_idle_time_001', 'randomfiletree_random_string_001', 'fishbase_gen_random_str_001']


def status():
    completed = {}
    for path in (ROOT / 'review/rules_v2/accepted').glob('*.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        task = row['task_id']
        assert task in TASKS and task not in completed
        assert row['reviewer_type'] == 'human' and row['reviewer']
        assert row['human_verdict'] in ('preserved', 'not_preserved', 'uncertain') and row['human_reason']
        for variant in ('risk', 'transformed'):
            actual = (ROOT / 'data/development_v2' / task / (variant + '.py')).read_bytes()
            assert row['code_sha256'][variant] == hashlib.sha256(actual).hexdigest()
        completed[task] = {'verdict': row['human_verdict'], 'evidence': str(path.relative_to(ROOT))}
    return {'completed': completed, 'pending': [t for t in TASKS if t not in completed],
            'status': 'complete' if len(completed) == len(TASKS) else 'partial' if completed else 'pending'}
