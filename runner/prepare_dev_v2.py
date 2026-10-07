"""Frozen development v2 rules + expanded targets. No human labels inferred."""
import hashlib
import json
import random
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.prepare_dev_v1 import extract
from runner.prompting import build_prompt
from methods.prevent_v2 import transform

def main():
    dest=ROOT/'runs/development_v2'
    if (dest/'schedule.json').exists(): raise SystemExit('Refusing to replace frozen v2 schedule')
    old=json.loads((ROOT/'runs/development_v1/schedule.json').read_text(encoding='utf-8'))
    tasks=old['tasks']
    tale=next(t for t in tasks if t['project_id']=='Tale')
    tale.update(clock_semantics='synchronous_elapsed_duration',clock_dependency='time',perturbation='clock_combined_v2')
    lith=next(t for t in tasks if t['project_id']=='lithoxyl')
    lith['random_semantics']='population_estimation'
    specs=[('RandomFileTree','randomfiletree.core','random_string','randomfiletree/core.py',
            "random_string(3, 3)","'0CQ'",
            "from randomfiletree.core import random_string\n\ndef test_example():\n    value = random_string(3, 3)\n    assert len(value) == 3\n    assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in value)\n",
            'random_string(min_length=5, max_length=10) returns an uppercase ASCII/digit string. Length is selected inclusively using random.randint; characters use random.choice. The example is a seed-0 regression case on Python 3.11, not an unconditional exact-string API guarantee.'),
           ('fishbase','fishbase.fish_random','gen_random_str','fishbase/fish_random.py',
            "gen_random_str(4, 4, prefix='p_', suffix='_s')","'p_WAcq_s'",
            "from fishbase.fish_random import gen_random_str\n\ndef test_example():\n    value = gen_random_str(4, 4, prefix='p_', suffix='_s')\n    assert value.startswith('p_')\n    assert value.endswith('_s')\n    assert len(value) == 8\n    assert value[2:-2].isalpha()\n",
            'gen_random_str(min_length, max_length, prefix=None, suffix=None, has_letter=True, has_digit=False, has_punctuation=False) generates a random middle string of inclusive selected length, then appends prefix/suffix. Length arguments must be int with min<=max; at least one character class must be enabled. Uses random.randint and random.sample. The example is a seed-0 regression case on Python 3.11, not an unconditional exact-string API guarantee.')]
    for name,module,target,file,call,expected,clean,contract in specs:
        provenance=json.loads((ROOT/'data/sources'/f'{name}_provenance.json').read_text(encoding='utf-8'))
        path=ROOT/provenance['project_path']/file
        source=extract(path,target)
        task_id=name.lower()+'_'+target+'_001'
        tasks.append({'task_id':task_id,'project_id':name,'project_path':provenance['project_path'],
            'commit':provenance['commit'],'target':module+'.'+target,'target_module':module,'target_qualname':target,
            'target_source':source,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'risk_type':'randomness','rng_dependency':'random','random_semantics':'seeded_example_regression',
            'perturbation':'random_state','dataset_layer':'constructed_seeded_regression',
            'provenance':'Real immutable project; constructed module-seed scope risk. Seed 0 fixed before observing outcomes; expected literal from first seed-0 call. Not an unchanged historical flaky test. Related historical lead checked separately.',
            'eligibility':'development diagnostic; human intent-equivalence review pending',
            'human_review_status':'pending','allowed_imports':[module.split('.')[0],'pytest','random','string'],
            'contract':contract+f' You may use pytest monkeypatch to isolate {module}.random with random.Random(seed), never replace the target function. No file access needed.',
            'risk_example':f"import random\nfrom {module} import {target}\n\nrandom.seed(0)\n\ndef test_example():\n    assert {call} == {expected}\n",
            'clean_example':clean})
    for task in tasks:
        tdest=ROOT/'data/development_v2'/task['task_id']
        save(tdest/'task.json',task)
        for ctx in ['risk','clean']:
            (tdest/(ctx+'.py')).write_text(task[ctx+'_example'],encoding='utf-8')
        out,evidence=transform(task['target_source'],task['risk_example'],task)
        (tdest/'transformed.py').write_text(out,encoding='utf-8')
        save(tdest/'transformation.json',evidence)
    selected=[t for t in tasks if t['project_id'] in ['Tale','RandomFileTree','fishbase']]
    cfg=json.loads((ROOT/'configs/models_v1.json').read_text(encoding='utf-8'))
    warning=(ROOT/'prompts/warning.txt').read_text(encoding='utf-8')
    cells=[]
    for task in selected:
        for model in cfg['models']:
            for ctx in ['risk','clean']:
                for method in ['B0','B1','M']:
                    prompt,evidence=build_prompt(task,ctx,method,warning,transformer=transform)
                    cells.append({'task_id':task['task_id'],'model_id':model,'context':ctx,'method':method,
                        'generation_round':1,'prompt':prompt,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                        'transformation':evidence})
    random.Random(20261007).shuffle(cells)
    for i,c in enumerate(cells): c['output_id']=f'v{i+1:03d}'
    save(dest/'schedule.json',{'tasks':tasks,'generation_tasks':[t['task_id'] for t in selected],'config':cfg,
        'cells':cells,'execution_seeds':list(range(30)),'scope':'36-call diagnostic of new rules, not confirmatory comparison. 5 total curated targets; 3 targets generated this batch.',
        'method_source_sha256':hashlib.sha256((ROOT/'methods/prevent_v2.py').read_bytes()).hexdigest(),
        'prompt_builder_sha256':hashlib.sha256((ROOT/'runner/prompting.py').read_bytes()).hexdigest(),
        'execution':'30 processes; RNG entry seeds 0..29. Tale: alternate no delay / 150ms getter-entry + 20ms send-return gap. No natural-rate claim.',
        'human_review':'User agreed to review; no human labels received yet.'})
    save(ROOT/'data/development_v2/index.json',{'distinct_targets':len(tasks),'distinct_projects':len({t['project_id'] for t in tasks}),
         'tasks':[{k:t[k] for k in ['task_id','target','project_id','dataset_layer','human_review_status']} for t in tasks],
         'formal_dataset':False,'planned_development_targets':24})
    print('Frozen',len(tasks),'targets;',len(cells),'generation cells')
if __name__=='__main__': main()
