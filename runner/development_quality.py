"""Post-generation, hand-seeded diagnostic mutants; not a formal mutation score."""
import concurrent.futures
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.development_v1 import RUN,config
from runner.prepare import save
from runner.evaluate import evaluate

MUTATIONS={
 'Tale':('tale/pubsub.py',{
    'idle_always_zero':('return time.time() - self.last_event','return 0.0'),
    'idle_reversed':('return time.time() - self.last_event','return self.last_event - time.time()'),
    'send_does_not_reset':('        self.last_event = time.time()\n        if synchronous:', '        self.last_event = self.last_event\n        if synchronous:')}),
 'lithoxyl':('lithoxyl/moment.py',{
    'mean_unchanged':('self._mean = self._mean + delta_n','self._mean = self._mean'),
    'second_moment_unchanged':('self._m2 = m2 + term','self._m2 = m2'),
    'count_plus_two':('self._count += 1','self._count += 2')})}

def prepare(task):
    project=task['project_id']
    if project=='penman':
        return {p.name:p for p in (ROOT/'runs/quality_mutants').iterdir() if p.is_dir()}
    filename,mutations=MUTATIONS[project]
    result={}
    for name,(before,after) in mutations.items():
        dest=RUN/'quality_mutants'/project/name
        source=ROOT/task['project_path']
        if not dest.exists():
            package=filename.split('/')[0]
            shutil.copytree(source/package,dest/package,ignore=shutil.ignore_patterns('__pycache__'))
            path=dest/filename
            original=path.read_text(encoding='utf-8')
            assert original.count(before)==1
            path.write_text(original.replace(before,after),encoding='utf-8')
            save(dest/'mutation.json',{'source_file':filename,'before':before,'after':after,'origin_commit':task['commit']})
        result[name]=dest
    return result

def assess(test,dest,task,mutants):
    result={}
    for name,path in mutants.items():
        cfg={**config(task),'project_path':str(path),'hash_seeds':[0,1,2]}
        outcome=evaluate(test,dest/name,cfg,workers=3)
        # Strict diagnostic kill: all runs fail, no collection/infra exceptions.
        result[name]={'killed':outcome['status']=='persistent_failure','evaluation':outcome}
    save(dest/'summary.json',{'diagnostic_only':True,'mutants':result,
        'killed':sum(r['killed'] for r in result.values()),'total':len(result)})
    print(dest.name,sum(r['killed'] for r in result.values()),'/',len(result),flush=True)

def main():
    schedule=json.loads((RUN/'schedule.json').read_text(encoding='utf-8'))
    tasks={t['task_id']:t for t in schedule['tasks']}
    mutants={key:prepare(t) for key,t in tasks.items()}
    jobs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for key,task in tasks.items():
            test=ROOT/'data/development_v1'/key/'clean.py'
            jobs.append(pool.submit(assess,test,RUN/'quality_controls'/key,task,mutants[key]))
        for cell in schedule['cells']:
            out=RUN/'outputs'/cell['output_id']
            summary=out/'evaluation/summary.json'
            if not summary.exists() or json.loads(summary.read_text(encoding='utf-8'))['status']!='stable_proxy_valid': continue
            jobs.append(pool.submit(assess,out/'test_generated.py',RUN/'quality'/cell['output_id'],tasks[cell['task_id']],mutants[cell['task_id']]))
        for job in jobs: job.result()
if __name__=='__main__': main()
