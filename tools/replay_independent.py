"""Re-execute the frozen external probes in a new directory, preserving records."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',required=True)
    parser.add_argument('--smoke',action='store_true',help='Run each reference and mutant once instead of the full protocol.')
    args=parser.parse_args()
    dest=Path(args.destination).resolve()
    if dest.exists():raise SystemExit('Destination must be new; existing evidence will not be overwritten.')
    frozen=json.loads((ROOT/'runs/independent_validation_v1/frozen.json').read_text(encoding='utf-8'))
    names=list(frozen['hashes'])+['runs/independent_validation_v1/frozen.json','runs/independent_validation_v1/frozen.sha256']
    for name in names:
        out=dest/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,out)
    (dest/'analysis').mkdir()
    script=dest/'runner/independent_validation_v1.py'
    if not args.smoke:
        subprocess.run([sys.executable,str(script),'run'],check=True,cwd=dest)
        return
    spec=importlib.util.spec_from_file_location('external_replay',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify()
    results=[]
    for task in frozen['tasks']:
        for variant in ['reference','mutant']:
            r=module.run_one(task,variant,0);results.append(r)
            assert r['status']==('pass' if variant=='reference' else 'fail') and r['target_calls']>0,r
    (dest/'smoke_result.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print('PASS: clean-directory replay of three reference tests and three diagnostic mutants; all real targets called.')


if __name__=='__main__':main()
