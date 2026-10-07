"""Freeze an expanded diagnostic set before generation; separate provenance layers."""
import ast
import hashlib
import json
from pathlib import Path
import random
import sys
import textwrap
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from methods.prevent_v1 import transform

def extract(path,name):
    text=path.read_text(encoding='utf-8')
    node=next(n for n in ast.parse(text).body if getattr(n,'name',None)==name)
    return textwrap.dedent('\n'.join(text.splitlines()[node.lineno-1:node.end_lineno]))

def main():
    run=ROOT/'runs/development_v1'
    if (run/'schedule.json').exists():
        raise SystemExit('Frozen schedule already exists')
    pen=json.loads((ROOT/'data/tasks/penman_variables.json').read_text(encoding='utf-8'))
    pen.update(project_path='vendor/penman-'+pen['commit'],target_module='penman.graph',target_qualname='Graph.variables',
        allowed_imports=['penman','pytest','collections'],perturbation='hash',
        eligibility='constructed pipeline control; not historical flaky test')
    tasks=[pen]
    tale=json.loads((ROOT/'data/sources/Tale_provenance.json').read_text(encoding='utf-8'))
    path=ROOT/tale['project_path']/'tale/pubsub.py'
    risk='''from tale.pubsub import topic
import time

def test_example():
    s = topic('example_idle')
    assert s.idle_time < 0.1
    time.sleep(0.2)
    assert s.idle_time > 0.1
    s.send('event')
    assert s.idle_time < 0.1
'''
    clean='''from tale.pubsub import topic
import tale.pubsub
from types import SimpleNamespace

def test_example(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(tale.pubsub, 'time', SimpleNamespace(time=lambda: clock[0]))
    s = topic('example_idle')
    assert s.idle_time == 0.0
    clock[0] = 100.2
    assert abs(s.idle_time - 0.2) < 1e-10
    s.send('event')
    assert s.idle_time == 0.0
'''
    tasks.append({'task_id':'tale_topic_idle_time_001','project_id':'Tale','commit':tale['commit'],
        'project_path':tale['project_path'],'target':'tale.pubsub.Topic.idle_time',
        'target_module':'tale.pubsub','target_qualname':'Topic.idle_time','risk_type':'time',
        'dataset_layer':'historical_risk_adapted','eligibility':'diagnostic development only; human review pending',
        'provenance':'IDoFT test_idletime converted from unittest to pytest, isolated topic name; original source retained. Ordinary 30/30 pass; explicit scheduling delay 15/30 fail. No claim of spontaneous reproduction.',
        'source_test':tale['test'],'target_source':extract(path,'Topic')+'\n\n'+extract(path,'topic'),
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'contract':"Use tale.pubsub.topic(name) to get a Topic. idle_time is the current clock time minus last_event. Construction and send reset last_event; sync does not. All topics in each process share a registry. You may substitute the external clock dependency with pytest monkeypatch (e.g. tale.pubsub.time), but never replace Topic methods or idle_time. The test may request the monkeypatch fixture.",
        'risk_example':risk,'clean_example':clean,'allowed_imports':['tale','pytest','time','types','unittest'],
        'perturbation':'clock_delay','human_review_status':'pending'})
    lith=json.loads((ROOT/'data/sources/lithoxyl_provenance.json').read_text(encoding='utf-8'))
    path=ROOT/lith['project_path']/'lithoxyl/moment.py'
    risk='''import random
from lithoxyl.moment import MomentAccumulator

def test_example():
    acc = MomentAccumulator()
    for value in [random.gauss(10, 4) for _ in range(100)]:
        acc.add(value)
    assert abs(acc.mean - 10) < 0.1
'''
    clean='''from lithoxyl.moment import MomentAccumulator

def test_example():
    acc = MomentAccumulator()
    for value in [6, 10, 14]:
        acc.add(value)
    assert acc.mean == 10
'''
    tasks.append({'task_id':'lithoxyl_moment_add_001','project_id':'lithoxyl','commit':lith['commit'],
        'project_path':lith['project_path'],'target':'lithoxyl.moment.MomentAccumulator.add',
        'target_module':'lithoxyl.moment','target_qualname':'MomentAccumulator.add','risk_type':'randomness',
        'dataset_layer':'historical_inspired_constructed','eligibility':'diagnostic development only; not natural pair',
        'provenance':'Inspired by test_momentacc_norm Gaussian sample/population assertion. Sample size, tolerance, and assertions deliberately changed; defective signed relative-comparison helper excluded. NOT an unchanged historical test or reproduction. Clean example is a researcher-written reference, never M input.',
        'source_test':lith['test'],'target_source':extract(path,'MomentAccumulator'),
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'contract':'MomentAccumulator.add(value) incorporates one numeric observation. count counts observations; mean is the arithmetic sample mean; variance uses n-1. min/max are internal. Public properties include count, mean, variance, std_dev, skewness, kurtosis. Empty properties default to -0.0 where not computable. Test add through its observable effects, without replacing implementation. Floating arithmetic may require pytest.approx.',
        'risk_example':risk,'clean_example':clean,'allowed_imports':['lithoxyl','pytest','random','math','statistics'],
        'perturbation':'random_state','human_review_status':'pending'})
    for task in tasks:
        dest=ROOT/'data/development_v1'/task['task_id']
        save(dest/'task.json',task)
        (dest/'risk.py').write_text(task['risk_example'],encoding='utf-8')
        (dest/'clean.py').write_text(task['clean_example'],encoding='utf-8')
        out,evidence=transform(task['target_source'],task['risk_example'],task)
        (dest/'transformed.py').write_text(out,encoding='utf-8')
        save(dest/'transformation.json',evidence)
    cfg=json.loads((ROOT/'configs/models_v1.json').read_text(encoding='utf-8'))
    cells=[]
    warning=(ROOT/'prompts/warning.txt').read_text(encoding='utf-8')
    base="Write exactly one new pytest test function for the target, using a different input or boundary from the example. Call the actual implementation and assert meaningful behavior. Do not modify or replace the target, skip tests, or swallow exceptions. Output only runnable Python including imports, no explanation. Do not access files, network, processes, or environment. Use only the listed modules and pytest."
    for task in tasks:
        for model in cfg['models']:
            for context in ['risk','clean']:
                for method in ['B0','B1','B2','M']:
                    shown=task[context+'_example']
                    evidence={'changed':False}
                    if method=='M': shown,evidence=transform(task['target_source'],shown,task)
                    if method=='B2': shown='[Example omitted]'
                    prompt=f"{base}\n{warning if method=='B1' else ''}\nAllowed modules: {', '.join(task['allowed_imports'])}\nContract:\n{task['contract']}\nTarget source:\n{task['target_source']}\nExample:\n{shown}"
                    cells.append({'task_id':task['task_id'],'model_id':model,'context':context,'method':method,
                        'generation_round':1,'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'transformation':evidence})
    random.Random(20261005).shuffle(cells)
    for i,c in enumerate(cells): c['output_id']=f'd{i+1:03d}'
    save(run/'schedule.json',{'config':cfg,'tasks':tasks,'cells':cells,'execution_seeds':list(range(30)),
        'scope':'48-call development diagnostic; one generation per cell. M abstains on time/randomness; no claim of complete three-risk method.',
        'extraction':'Uniform boundary opening and optional closing markdown fence removal; no repair.',
        'execution':'30 fresh processes: hash seeds 0..29; RNG seeded at test entry for random task; 0/150ms delay on alternating seeds at idle_time call for time task. Controlled robustness, not natural failure frequency.',
        'inference':'3 distinct targets, 3 projects; no significance test. B2 duplicate prompts across context labels are repeated generations, not distinct tasks.'})
    print('Frozen',len(tasks),'tasks',len(cells),'cells')
if __name__=='__main__': main()
