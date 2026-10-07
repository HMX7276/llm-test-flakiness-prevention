"""Fresh process/directory per hash seed. Local pilot only; not a security sandbox."""
import argparse
import ast
import collections
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save


def screen(code, allowed_imports=None, target_name='variables'):
    """Conservative execution gate, separate from semantic correctness."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"runnable":False,"reason":"syntax_error","quality_proxy":False}
    imports = []
    prohibited = []
    assertions = []
    for n in ast.walk(tree):
        if isinstance(n,ast.Import):
            imports.extend(a.name.split('.')[0] for a in n.names)
        if isinstance(n,ast.ImportFrom):
            imports.append((n.module or '').split('.')[0])
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {
            "eval","exec","compile","open","__import__","getattr","setattr","delattr","globals","locals","breakpoint","input"}:
            prohibited.append(n.func.id)
        if isinstance(n,ast.Attribute) and (n.attr.startswith('__') or n.attr in {"skip","skipif","xfail"}):
            prohibited.append(n.attr)
        if isinstance(n,(ast.Try,ast.While,ast.With,ast.AsyncWith)):
            prohibited.append(type(n).__name__)
        if isinstance(n,ast.Assert):
            assertions.append(n)
    unsupported = sorted(set(imports)-set(allowed_imports or {"penman","pytest","collections"}))
    if unsupported or prohibited:
        return {"runnable":False,"reason":"execution_review_required","unsupported_imports":unsupported,"prohibited":prohibited,"quality_proxy":False}
    tests = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
    calls_target = any((isinstance(n,ast.Attribute) and n.attr==target_name) if target_name=='idle_time' else
                       (isinstance(n,ast.Call) and ((isinstance(n.func,ast.Attribute) and n.func.attr==target_name)
                                                   or (isinstance(n.func,ast.Name) and n.func.id==target_name)))
                       for n in ast.walk(tree))
    meaningful = any(not isinstance(n.test,ast.Constant) for n in assertions)
    return {"runnable":True,"reason":"screen_passed","quality_proxy":len(tests)==1 and calls_target and meaningful,
            "test_function_count":len(tests),"assertion_count":len(assertions),"target_call_in_ast":calls_target,
            "semantic_review":"pending"}


def run_one(test_path, dest, seed, cfg, collect=False):
    dest.mkdir(parents=True,exist_ok=True)
    local = dest / "test_subject.py"
    shutil.copyfile(test_path,local)
    project = Path(cfg['project_path']) if cfg.get('project_path') else ROOT / "vendor" / ("penman-"+cfg["commit"])
    env = {k:v for k,v in os.environ.items() if k.upper() in {"SYSTEMROOT","WINDIR","COMSPEC","PATHEXT"}}
    env.update({"PATH":str(Path(sys.executable).parent),"PYTHONPATH":os.pathsep.join([str(project),str(ROOT/"runner")]),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONHASHSEED":str(seed),"PYTHONIOENCODING":"utf-8",
                "PYTHONDONTWRITEBYTECODE":"1","TEMP":str(dest),"TMP":str(dest),
                "EXPERIMENT_TRACE_PATH":str(dest/"trace.json")})
    if cfg.get('target_module'):
        env.update({'TRACE_TARGET_MODULE':cfg['target_module'],'TRACE_TARGET_QUALNAME':cfg['target_qualname'],
                    'DEV_PERTURBATION':cfg.get('perturbation','hash'),'DEV_SEED':str(seed)})
    command = [sys.executable,"-m","pytest","-q","-p","no:cacheprovider","-p","trace_plugin",str(local)]
    if collect:
        command.append("--collect-only")
    start = time.monotonic()
    record = {"run_id":dest.name,"hash_seed":seed,"protocol":cfg.get('perturbation','hash_seed_sweep_v0'),"collect_only":collect,
              "artifact_hash":hashlib.sha256(test_path.read_bytes()).hexdigest()}
    try:
        p = subprocess.run(command,cwd=dest,env=env,capture_output=True,timeout=cfg["execution_timeout_seconds"])
        stdout = p.stdout.decode('utf-8',errors='replace')
        stderr = p.stderr.decode('utf-8',errors='replace')
        record['return_code'] = p.returncode
        trace_path = dest/'trace.json'
        trace = json.loads(trace_path.read_text(encoding='utf-8')) if trace_path.exists() else {}
        record.update({"target_calls":trace.get('target_calls',0),"collected":trace.get('collected',0)})
        phases = trace.get('reports',[])
        if trace.get('collection_errors') or (collect and p.returncode != 0):
            status = 'collection_failure'
        elif not trace:
            status = 'infrastructure_error'
        elif collect:
            status = 'collection_passed' if record['collected'] else 'no_tests'
        elif any(r['outcome']=='skipped' for r in phases):
            status = 'skip'
        elif any(r['when'] != 'call' and r['outcome']=='failed' for r in phases):
            status = 'setup_teardown_error'
        elif any(r['when']=='call' and r['outcome']=='failed' for r in phases):
            status = 'fail'
        elif p.returncode==0 and any(r['when']=='call' and r['outcome']=='passed' for r in phases):
            status = 'pass'
        else:
            status = 'infrastructure_error'
        record['status'] = status
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b'').decode('utf-8',errors='replace')
        stderr = (exc.stderr or b'').decode('utf-8',errors='replace')
        record.update({"status":"timeout","return_code":None})
    record['duration'] = time.monotonic()-start
    (dest/'stdout.txt').write_text(stdout,encoding='utf-8')
    (dest/'stderr.txt').write_text(stderr,encoding='utf-8')
    record['stdout'] = str((dest/'stdout.txt').relative_to(ROOT))
    record['stderr'] = str((dest/'stderr.txt').relative_to(ROOT))
    save(dest/'execution.json',record)
    return record


def classify(records, quality):
    if not records:
        return {"status":"incomplete","counts":{},"executions":0,"has_pass":False,"semantic_review":"pending"}
    counts = collections.Counter(r['status'] for r in records)
    exceptional = set(counts)-{'pass','fail'}
    if exceptional:
        status = 'execution_exception'
    elif counts['pass'] and counts['fail']:
        status = 'observed_unstable'
    elif counts['fail']==len(records):
        status = 'persistent_failure'
    elif counts['pass']==len(records):
        status = 'stable_proxy_valid' if quality and all(r.get('target_calls',0)>0 for r in records) else 'stable_proxy_invalid'
    else:
        status = 'incomplete'
    return {"status":status,"counts":dict(counts),"executions":len(records),
            "has_pass":bool(counts['pass']),"semantic_review":"pending"}


def evaluate(test_path, dest, cfg, workers=4):
    if (dest/'summary.json').exists():
        return json.loads((dest/'summary.json').read_text())
    gate = screen(test_path.read_text(encoding='utf-8'),cfg.get('allowed_imports'),cfg.get('target_qualname','variables').split('.')[-1])
    save(dest/'screen.json',gate)
    if not gate['runnable']:
        summary = {"status":gate['reason'],"executions":0,"counts":{}}
    else:
        collection = run_one(test_path,dest/'collection',0,cfg,collect=True)
        if collection['status']!='collection_passed':
            summary = {"status":collection['status'],"executions":0,"counts":{}}
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                jobs = [pool.submit(run_one,test_path,dest/f"run_{i:03d}",seed,cfg) for i,seed in enumerate(cfg['hash_seeds'])]
                records = [j.result() for j in jobs]
            summary = classify(records,gate['quality_proxy'])
            save(dest/'executions.json',records)
    summary['code_sha256'] = hashlib.sha256(test_path.read_bytes()).hexdigest()
    save(dest/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--controls',action='store_true')
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    cfg=json.loads((ROOT/'runs/pilot_v0/schedule.json').read_text())['config']
    if args.controls:
        for name in ['risk','clean','transformed']:
            result=evaluate(ROOT/f'data/tasks/test_example_{name}.py',ROOT/f'runs/controls/{name}',cfg,args.workers)
            print(name,result,flush=True)
    else:
        for dest in sorted((ROOT/'runs/pilot_v0/outputs').glob('g*')):
            if not (dest/'record.json').exists():
                continue  # Generation may still be in flight.
            record=json.loads((dest/'record.json').read_text())
            if record['status']!='api_success':
                continue
            result=evaluate(dest/'test_generated.py',dest/'evaluation',cfg,args.workers)
            print(dest.name,result,flush=True)


if __name__=='__main__':
    main()
