"""Fresh-process historical test verification with explicit perturbation labels."""
import argparse
from collections import Counter
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

def execute(candidate, mode, seed):
    name=candidate['project'].split('/')[-1]
    evidence_root=(ROOT/candidate.get('evidence_root','runs/curation_v1')).resolve()
    if not evidence_root.is_relative_to((ROOT/'runs').resolve()): raise ValueError('Evidence must stay within runs')
    dest=evidence_root/name/mode/f'run_{seed:03d}'
    if (dest/'execution.json').exists():
        return json.loads((dest/'execution.json').read_text(encoding='utf-8'))
    dest.mkdir(parents=True,exist_ok=True)
    project=ROOT/candidate['project_path']
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
    env.update({'PYTHONPATH':os.pathsep.join([str(project),str(ROOT/'runner')]),
        'PYTHONHASHSEED':str(seed),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1',
        'PYTHONIOENCODING':'utf-8','TEMP':str(dest),'TMP':str(dest),'CURATION_MODE':mode,'CURATION_SEED':str(seed)})
    if candidate.get('environment_profile') == 'local_scientific_cache_v1':
        # Explicit profile, only for new scientific candidates; no user-home access.
        for key, folder in [('NLTK_DATA','nltk_data'),('MPLCONFIGDIR','mpl_config'),('USERPROFILE','profile')]:
            path=dest/folder
            path.mkdir(exist_ok=True)
            env[key]=str(path)
    cmd=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','-p','curation_plugin',
         str(project/candidate['test']),'--junitxml='+str(dest/'junit.xml')]
    if mode=='isolated_clean_options':
        cmd.extend(['-o','addopts='])
    if mode=='repeat_same_process':
        cmd.extend([str(project/candidate['test']),'-o','addopts=','--keep-duplicates'])
    start=time.monotonic()
    record={'seed':seed,'mode':mode,'test':candidate['test'],'command':cmd,
            'environment_profile':candidate.get('environment_profile','minimal_v1')}
    try:
        p=subprocess.run(cmd,cwd=dest,env=env,capture_output=True,timeout=40)
        (dest/'stdout.txt').write_bytes(p.stdout)
        (dest/'stderr.txt').write_bytes(p.stderr)
        cases=ET.parse(dest/'junit.xml').findall('.//testcase') if (dest/'junit.xml').exists() else []
        status='infrastructure_error'
        if any(c.find('error') is not None for c in cases): status='collection_or_setup_error'
        elif any(c.find('failure') is not None for c in cases): status='fail'
        elif any(c.find('skipped') is not None for c in cases): status='skip'
        elif p.returncode==0 and cases: status='pass'
        record.update(status=status,return_code=p.returncode)
    except subprocess.TimeoutExpired as e:
        (dest/'stdout.txt').write_bytes(e.stdout or b'')
        (dest/'stderr.txt').write_bytes(e.stderr or b'')
        record['status']='timeout'
    record['duration']=time.monotonic()-start
    save(dest/'execution.json',record)
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('projects',nargs='+')
    p.add_argument('--mode',choices=['isolated','isolated_clean_options','random_state','scheduler_delay'],default='isolated')
    p.add_argument('--runs',type=int,default=30)
    args=p.parse_args()
    for name in args.projects:
        candidate=json.loads((ROOT/'data/sources'/f'{name}_provenance.json').read_text(encoding='utf-8'))
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            records=list(pool.map(lambda seed:execute(candidate,args.mode,seed),range(args.runs)))
        summary={'candidate':candidate,'mode':args.mode,'runs':records,'counts':dict(Counter(r['status'] for r in records)),
            'interpretation':'Perturbations are explicit diagnostics, not observed historical failure frequencies.'}
        save(ROOT/'runs/curation_v1'/name/args.mode/'summary.json',summary)
        print(name,args.mode,summary['counts'],flush=True)
