import ast
import json
from pathlib import Path
from methods.prevent_v2 import transform,fingerprint_assertions
ROOT=Path(__file__).resolve().parents[1]
TALE=json.loads((ROOT/'data/development_v1/tale_topic_idle_time_001/task.json').read_text(encoding='utf-8'))
TIME={**TALE,'clock_semantics':'synchronous_elapsed_duration','clock_dependency':'time'}
RNG={'target_module':'randomfiletree.core','target_qualname':'random_string','risk_type':'randomness',
     'random_semantics':'seeded_example_regression','rng_dependency':'random'}
RISK="import random\nfrom randomfiletree.core import random_string\nrandom.seed(0)\ndef test_a():\n    assert random_string(3,3) == '0CQ'\n"
SOURCE='def random_string(a,b):\n    n=random.randint(a,b)\n    return str(n)\n'

def test_time_preserves_every_assertion_and_removes_wall_sleep():
    before=TIME['risk_example']
    out,e=transform(TIME['target_source'],before,TIME)
    assert e['changed']
    assert fingerprint_assertions(ast.parse(before))==fingerprint_assertions(ast.parse(out))
    assert 'time.sleep' not in out
    assert "monkeypatch.setattr(_risk_module, 'time'" in out
    assert '_risk_clock[0] += 0.2' in out

def test_time_rejects_calendar_or_performance_contract():
    out,e=transform(TIME['target_source'],TIME['risk_example'],{**TIME,'clock_semantics':'performance_deadline'})
    assert not e['changed'] and out==TIME['risk_example']

def test_time_rejects_external_real_clock_sampling():
    code=TIME['risk_example'].replace("    s.send('event')","    stamp = time.time()\n    s.send('event')")
    assert not transform(TIME['target_source'],code,TIME)[1]['changed']

def test_rng_keeps_seed_and_exact_assertion_without_seed_search():
    out,e=transform(SOURCE,RISK,RNG)
    assert e['changed'] and e['seed_from_example']==0
    assert 'random.Random(0)' in out and 'random.seed' not in out
    assert fingerprint_assertions(ast.parse(RISK))==fingerprint_assertions(ast.parse(out))

def test_rng_refuses_seed_invention():
    assert not transform(SOURCE,RISK.replace('random.seed(0)\n',''),RNG)[1]['changed']

def test_rng_refuses_population_oracle():
    assert not transform(SOURCE,RISK,{**RNG,'random_semantics':'population_estimation'})[1]['changed']

def test_rng_refuses_shadowing():
    code=RISK.replace('    assert','    random_string = fake\n    assert')
    assert not transform(SOURCE,code,RNG)[1]['changed']

def test_lithoxyl_population_assertion_remains_exactly_unchanged():
    task=json.loads((ROOT/'data/development_v1/lithoxyl_moment_add_001/task.json').read_text(encoding='utf-8'))
    out,e=transform(task['target_source'],task['risk_example'],task)
    assert not e['changed'] and out==task['risk_example']
