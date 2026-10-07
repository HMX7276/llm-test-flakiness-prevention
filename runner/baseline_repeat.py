import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save


def one(commit,seed):
    project=ROOT/'vendor'/('penman-'+commit)
    dest=ROOT/'runs/baseline_repeat'/commit/f'run_{seed:03d}'
    dest.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
    env.update({'PYTHONPATH':str(project),'PYTHONHASHSEED':str(seed),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
                'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8','TEMP':str(dest),'TMP':str(dest)})
    start=time.monotonic()
    p=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',str(project/'tests'),
                      '--junitxml='+str(dest/'junit.xml')],cwd=dest,env=env,capture_output=True,timeout=30)
    (dest/'stdout.txt').write_bytes(p.stdout)
    (dest/'stderr.txt').write_bytes(p.stderr)
    return {'seed':seed,'return_code':p.returncode,'duration':time.monotonic()-start}


if __name__=='__main__':
    commits=['7770dfe14b3d0d197cedc6640f3ff7e3bd695726','e83cf6d006724d72a3e19a955aad94412da912b7']
    for commit in commits:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            records=list(pool.map(lambda seed:one(commit,seed),range(30)))
        result={'commit':commit,'protocol':'original_suite_fresh_process_hash_0_to_29',
                'runs':records,'passed_suites':sum(r['return_code']==0 for r in records)}
        save(ROOT/'runs/baseline_repeat'/commit/'summary.json',result)
        print(commit,result['passed_suites'],'/ 30 suites passed',flush=True)
