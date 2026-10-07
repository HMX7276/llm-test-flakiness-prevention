"""Control/mutant checks of rules, independent of generated outputs."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.development_v1 import config
from runner.evaluate import evaluate

MUTANTS={
 'RandomFileTree':('randomfiletree/core.py',{
    'wrong_length':('length = random.randint(min_length, max_length)','length = random.randint(min_length, max_length) + 1'),
    'constant_chars':('random.choice(string.ascii_uppercase + string.digits)',"'X'")}),
 'fishbase':('fishbase/fish_random.py',{
    'omit_prefix':("prefix = prefix if prefix else ''","prefix = ''"),
    'wrong_length':('random_str_len = random.randint(min_length, max_length)','random_str_len = random.randint(min_length, max_length) + 1')})}

def paths(task):
    if task['project_id']=='Tale':
        return {p.name:p for p in (ROOT/'runs/development_v1/quality_mutants/Tale').iterdir() if p.is_dir()}
    file,mutations=MUTANTS[task['project_id']]
    out={}
    for name,(before,after) in mutations.items():
        dest=ROOT/'runs/rule_validation_v2/mutants'/task['project_id']/name
        if not dest.exists():
            package=file.split('/')[0]
            shutil.copytree(ROOT/task['project_path']/package,dest/package,ignore=shutil.ignore_patterns('__pycache__'))
            path=dest/file
            text=path.read_text(encoding='utf-8')
            assert text.count(before)==1
            path.write_text(text.replace(before,after),encoding='utf-8')
            save(dest/'mutation.json',{'file':file,'before':before,'after':after,'commit':task['commit']})
        out[name]=dest
    return out

def one(task):
    dest=ROOT/'runs/rule_validation_v2'/task['task_id']
    folder=ROOT/'data/development_v2'/task['task_id']
    results={}
    for name,project in paths(task).items():
        cfg={**config(task),'project_path':str(project),'hash_seeds':[0,1,2]}
        results[name]={}
        for variant in ['clean','transformed']:
            result=evaluate(folder/(variant+'.py'),dest/name/variant,cfg,workers=3)
            results[name][variant]=result
    save(dest/'summary.json',{'task_id':task['task_id'],'diagnostic_mutants':results,
        'interpretation':'Small hand-seeded rule regression checks; not formal mutation score or human equivalence approval.'})
    print(task['task_id'],{k:{v:r['status'] for v,r in s.items()} for k,s in results.items()},flush=True)

if __name__=='__main__':
    schedule=json.loads((ROOT/'runs/development_v2/schedule.json').read_text(encoding='utf-8'))
    tasks=[t for t in schedule['tasks'] if t['project_id'] in ['Tale','RandomFileTree','fishbase']]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one,tasks))
