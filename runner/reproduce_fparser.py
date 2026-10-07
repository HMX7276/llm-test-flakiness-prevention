import concurrent.futures
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

COMMIT='4be91d2e1078fa5588e84a3299131f297afba675'
PROJECT=ROOT/'vendor'/('fparser-'+COMMIT)
TEST='src/fparser/one/tests/test_block_stmts.py::test_implicit_topyf'


def one(seed,mode='isolated'):
    base=ROOT/'runs/fparser_reproduction' if mode=='isolated' else ROOT/'runs/fparser_order_diagnostic'/mode
    dest=base/f'run_{seed:03d}'
    dest.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
    env.update({'PYTHONPATH':str(PROJECT/'src'),'PYTHONHASHSEED':str(seed),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1',
                'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8','TEMP':str(dest),'TMP':str(dest)})
    start=time.monotonic()
    try:
        target=str(PROJECT/TEST)
        predecessor=str(PROJECT/'src/fparser/one/tests/test_block_stmts.py::test_get_type_by_name_implicit')
        test_nodes=[target] if mode=='isolated' else ([predecessor,target] if mode=='predecessor_first' else [target,predecessor])
        p=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',*test_nodes,
                          '--junitxml='+str(dest/'junit.xml')],cwd=dest,env=env,capture_output=True,timeout=30)
        (dest/'stdout.txt').write_bytes(p.stdout)
        (dest/'stderr.txt').write_bytes(p.stderr)
        tree=ET.parse(dest/'junit.xml')
        cases=tree.findall('.//testcase')
        status='infrastructure_error'
        if any(c.find('error') is not None for c in cases):
            status='collection_or_setup_error'
        elif any(c.find('failure') is not None for c in cases):
            status='fail'
        elif any(c.find('skipped') is not None for c in cases):
            status='skip'
        elif p.returncode==0 and cases:
            status='pass'
        return {'seed':seed,'status':status,'return_code':p.returncode,'duration':time.monotonic()-start}
    except subprocess.TimeoutExpired:
        return {'seed':seed,'status':'timeout','duration':time.monotonic()-start}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['isolated','predecessor_first','target_first'],default='isolated')
    args=parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(lambda seed:one(seed,args.mode),range(30)))
    from collections import Counter
    result={'project':'fparser','commit':COMMIT,'test':TEST,'protocol':'fresh_process_hash_0_to_29','mode':args.mode,
            'runs':records,'counts':dict(Counter(r['status'] for r in records))}
    base=ROOT/'runs/fparser_reproduction' if args.mode=='isolated' else ROOT/'runs/fparser_order_diagnostic'/args.mode
    save(base/'summary.json',result)
    print(result['counts'])
