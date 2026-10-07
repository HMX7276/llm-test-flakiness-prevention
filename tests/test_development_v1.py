from methods.prevent_v1 import transform
from runner.evaluate import screen
from tests.test_protocol import SOURCE
from runner.prompting import build_prompt

CONTRACT={'target':'penman.graph.Graph.variables'}
CODE="from penman import Graph\ndef test_a():\n    g = Graph([('a', ':instance', 'alpha')])\n    assert list(g.variables()) == ['a']\n"

def test_proven_receiver_is_normalized():
    assert transform(SOURCE,CODE,CONTRACT)[1]['changed']

def test_unknown_receiver_is_not_normalized():
    assert not transform(SOURCE,CODE.replace("g = Graph([('a', ':instance', 'alpha')])","g = unrelated()"),CONTRACT)[1]['changed']

def test_rebound_receiver_is_not_normalized():
    assert not transform(SOURCE,CODE.replace('    assert','    g = unrelated()\n    assert'),CONTRACT)[1]['changed']

def test_shadowed_builtin_is_not_normalized():
    assert not transform(SOURCE,CODE.replace('    assert','    list = unrelated\n    assert'),CONTRACT)[1]['changed']

def test_random_and_time_abstain_without_oracle():
    assert transform('',CODE,{'target':'tale.pubsub.Topic.idle_time'})[0]==CODE

def test_property_target_screen():
    assert screen('from tale.pubsub import topic\ndef test_t():\n    s=topic("x")\n    assert s.idle_time >= 0\n',['tale'],'idle_time')['quality_proxy']

def test_deletion_baseline_retains_public_import_identity():
    task={'target':'lithoxyl.moment.MomentAccumulator.add','target_module':'lithoxyl.moment',
          'allowed_imports':['lithoxyl'],'contract':'sample mean','target_source':'class MomentAccumulator: pass'}
    # B2 must work without reading either example at all.
    prompt,_=build_prompt(task,'risk','B2')
    assert 'Import module: lithoxyl.moment' in prompt
    assert 'Fully qualified target: lithoxyl.moment.MomentAccumulator.add' in prompt
    assert '[Example omitted]' in prompt

def test_method_does_not_need_clean_oracle():
    task={'target':'penman.graph.Graph.variables','target_module':'penman.graph',
          'allowed_imports':['penman'],'contract':'set of source identifiers','target_source':SOURCE,'risk_example':CODE}
    prompt,evidence=build_prompt(task,'risk','M')
    assert evidence['changed']
    assert 'Counter' in prompt
