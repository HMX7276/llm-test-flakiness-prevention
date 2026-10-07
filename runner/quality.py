"""Development diagnostics: per-target branch coverage and four seeded mutants.

This is not the planned full mutation study; operators were chosen in development.
"""
import ast
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save
from runner.evaluate import run_one


def environment(project,dest):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
    env.update({'PYTHONPATH':str(project),'PYTHONHASHSEED':'0','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
                'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8','TEMP':str(dest),'TMP':str(dest)})
    return env


def coverage(test,dest,project):
    dest.mkdir(parents=True,exist_ok=True)
    env=environment(project,dest)
    cmd=[sys.executable,'-m','coverage','run','--branch','--source=penman','-m','pytest',
         '-q','-p','no:cacheprovider','--import-mode=importlib',str(test)]
    p=subprocess.run(cmd,cwd=dest,env=env,capture_output=True,timeout=45)
    (dest/'stdout.txt').write_bytes(p.stdout)
    (dest/'stderr.txt').write_bytes(p.stderr)
    if p.returncode:
        return {'status':'coverage_execution_failure','return_code':p.returncode}
    subprocess.run([sys.executable,'-m','coverage','json','-o','coverage.json'],cwd=dest,env=env,
                   capture_output=True,timeout=15,check=True)
    report=json.loads((dest/'coverage.json').read_text())
    graph=next(v for k,v in report['files'].items() if k.replace('\\','/').endswith('penman/graph.py'))
    fn=graph['functions']['Graph.variables']
    return {'status':'ok','target_summary':fn['summary'],'executed_lines':fn['executed_lines'],
            'missing_lines':fn['missing_lines'],'executed_branches':fn['executed_branches'],
            'missing_branches':fn['missing_branches']}


def mutants(project):
    original=(project/'penman/graph.py').read_text(encoding='utf-8')
    cls=next(n for n in ast.parse(original).body if isinstance(n,ast.ClassDef) and n.name=='Graph')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='variables')
    lines=original.splitlines(True)
    fn=''.join(lines[node.lineno-1:node.end_lineno])
    definitions={
        'empty_result':('return vs','return set()'),
        'omit_explicit_top':('vs.add(self._top)','pass'),
        'use_targets':('set(src for src, _, _ in self.triples)','set(tgt for _, _, tgt in self.triples)'),
        'omit_sources':('set(src for src, _, _ in self.triples)','set()'),
    }
    records=[]
    for name,(old,new) in definitions.items():
        dest=ROOT/'runs/quality_mutants'/name
        if not dest.exists():
            dest.mkdir(parents=True)
            shutil.copytree(project/'penman',dest/'penman',ignore=shutil.ignore_patterns('__pycache__'))
        assert fn.count(old)==1
        modified=''.join(lines[:node.lineno-1])+fn.replace(old,new)+''.join(lines[node.end_lineno:])
        compile(modified,'graph.py','exec')
        (dest/'penman/graph.py').write_text(modified,encoding='utf-8')
        records.append({'mutant_id':name,'project_path':str(dest),'old':old,'new':new,
                        'sha256':hashlib.sha256((dest/'penman/graph.py').read_bytes()).hexdigest()})
    save(ROOT/'runs/quality_mutants/manifest.json',{'type':'four_hand_seeded_development_mutants','mutants':records})
    return records


def main():
    cfg=json.loads((ROOT/'runs/pilot_v0/schedule.json').read_text())['config']
    project=ROOT/'vendor'/('penman-'+cfg['commit'])
    pool=mutants(project)
    baseline_dest=ROOT/'runs/quality_baseline'
    if not (baseline_dest/'summary.json').exists():
        baseline={'coverage':coverage(project/'tests',baseline_dest/'coverage',project),'mutants':{}}
        for mut in pool:
            dest=baseline_dest/mut['mutant_id']
            dest.mkdir(parents=True,exist_ok=True)
            env=environment(Path(mut['project_path']),dest)
            p=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','--import-mode=importlib',str(project/'tests')],
                             cwd=dest,env=env,capture_output=True,timeout=30)
            (dest/'stdout.txt').write_bytes(p.stdout)
            (dest/'stderr.txt').write_bytes(p.stderr)
            baseline['mutants'][mut['mutant_id']]={'return_code':p.returncode,'failed_suite':p.returncode==1}
        save(baseline_dest/'summary.json',baseline)
        print('Baseline quality:',baseline,flush=True)
    for record_path in sorted((ROOT/'runs/pilot_v0/outputs').glob('*/record.json')):
        dest=record_path.parent
        evaluated=dest/'evaluation/summary.json'
        if not evaluated.exists() or json.loads(evaluated.read_text())['status']!='stable_proxy_valid':
            continue
        if (dest/'quality/summary.json').exists():
            continue
        test=dest/'test_generated.py'
        quality={'coverage':coverage(test,dest/'quality/coverage',project),'mutants':{},
                 'scope':'development_diagnostic_only','kill_repeats':3}
        for mut in pool:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
                jobs=[workers.submit(run_one,test,dest/'quality'/mut['mutant_id']/f'run_{seed}',seed,
                                     dict(cfg,project_path=mut['project_path'])) for seed in range(3)]
                records=[j.result() for j in jobs]
            quality['mutants'][mut['mutant_id']]={'killed':all(r['status']=='fail' for r in records),
                                                  'outcomes':[r['status'] for r in records]}
        quality['killed']=sum(m['killed'] for m in quality['mutants'].values())
        quality['mutant_denominator']=len(pool)
        save(dest/'quality/summary.json',quality)
        print(dest.name,'diagnostic mutants killed',quality['killed'],'/',len(pool),flush=True)


if __name__=='__main__':
    main()
