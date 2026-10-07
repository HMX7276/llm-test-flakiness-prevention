"""Check reproducibility references and accidental credential copies without printing keys."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save


def main():
    schedule=json.loads((ROOT/'runs/pilot_v0/schedule.json').read_text(encoding='utf-8'))
    mismatches=[]
    records=0
    records_by_run={}
    for cell in schedule['cells']:
        assert hashlib.sha256(cell['prompt'].encode()).hexdigest()==cell['prompt_hash']
        dest=ROOT/'runs/pilot_v0/outputs'/cell['output_id']
        if not (dest/'record.json').exists():
            continue
        record=json.loads((dest/'record.json').read_text(encoding='utf-8'))
        records+=1
        if (dest/'test_generated.py').exists():
            if hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest()!=record['code_sha256']:
                mismatches.append(cell['output_id'])
    records_by_run['pilot_v0']=records
    for run_name in ['development_v1','development_v1_import_sensitivity','development_v2']:
        run=ROOT/'runs'/run_name
        if not (run/'schedule.json').exists():
            continue
        count=0
        frozen=json.loads((run/'schedule.json').read_text(encoding='utf-8'))
        for cell in frozen['cells']:
            assert hashlib.sha256(cell['prompt'].encode()).hexdigest()==cell['prompt_sha256']
            dest=run/'outputs'/cell['output_id']
            if not (dest/'record.json').exists():
                continue
            count+=1
            record=json.loads((dest/'record.json').read_text(encoding='utf-8'))
            if record.get('code_sha256') and hashlib.sha256((dest/'test_generated.py').read_bytes()).hexdigest()!=record['code_sha256']:
                mismatches.append(run_name+'/'+cell['output_id'])
        records_by_run[run_name]=count
        records+=count
    secrets=re.findall(r'(?m)^KEY\d+:\s*(\S+)',(ROOT/'api-key.txt').read_text(encoding='utf-8-sig'))
    leaked_paths=[]
    inspected=0
    dirs=['runner','methods','prompts','configs','runs','analysis','notes','data','paper','tests','review']
    extensions={'.py','.json','.jsonl','.txt','.log','.md','.tsv','.csv','.tex','.bib','.ps1','.xml','.html','.cjs'}
    for folder in dirs:
        for path in (ROOT/folder).rglob('*'):
            if not path.is_file() or path.suffix not in extensions:
                continue
            raw=path.read_bytes()
            inspected+=1
            if any(secret.encode() in raw for secret in secrets):
                leaked_paths.append(str(path.relative_to(ROOT)))
    code={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
          for folder in ['runner','methods','analysis','tests','prompts','configs']
          for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.txt','.cjs'}}
    sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (ROOT/'data/sources').glob('*') if p.is_file()}
    sources['data/idoft_py_data.csv']=hashlib.sha256((ROOT/'data/idoft_py_data.csv').read_bytes()).hexdigest()
    result={'generation_records_checked':records,'generation_records_by_run':records_by_run,'output_hash_mismatches':mismatches,
            'text_files_scanned':inspected,'credential_copy_paths':leaked_paths,
            'code_and_config_sha256':code,'source_sha256':sources}
    save(ROOT/'runs/artifact_verification.json',result)
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')},ensure_ascii=False))
    if mismatches or leaked_paths:
        raise SystemExit(1)


if __name__=='__main__':
    main()
