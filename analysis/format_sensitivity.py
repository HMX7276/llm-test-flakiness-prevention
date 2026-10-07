"""Post-hoc presentation-only extraction sensitivity; never overwrites v0 data."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.evaluate import evaluate
from runner.prepare import save


def unwrap(content):
    content=content.strip()
    # Only trim boundary markdown lines, no code edits or inferred statements.
    if re.match(r'^```(?:python)?\s*\n',content):
        content=re.sub(r'^```(?:python)?\s*\n','',content,count=1)
        if content.rstrip().endswith('```'):
            content=content.rstrip()[:-3].rstrip()
    return content+'\n'


if __name__=='__main__':
    frozen=json.loads((ROOT/'runs/pilot_v0/schedule.json').read_text())
    rows=[]
    for path in sorted((ROOT/'runs/pilot_v0/outputs').glob('*/record.json')):
        record=json.loads(path.read_text())
        if record['status']!='api_success':
            continue
        original=path.parent/'test_generated.py'
        code=unwrap((path.parent/'content.txt').read_text(encoding='utf-8'))
        if code.strip()==original.read_text(encoding='utf-8').strip():
            continue
        dest=ROOT/'runs/format_sensitivity'/path.parent.name
        dest.mkdir(parents=True,exist_ok=True)
        test=dest/'test_presentation_normalized.py'
        test.write_text(code,encoding='utf-8')
        summary=evaluate(test,dest/'evaluation',frozen['config'])
        rows.append({'output_id':path.parent.name,'original_sha256':record['code_sha256'],
                     'normalized_sha256':hashlib.sha256(test.read_bytes()).hexdigest(),'evaluation':summary})
    save(ROOT/'analysis/format_sensitivity.json',{'analysis_type':'post_hoc_presentation_only',
         'primary_results_unchanged':True,'uniform_rule':'Trim opening and optional closing markdown fence only',
         'changed_outputs':rows})
    print([(r['output_id'],r['evaluation']['status']) for r in rows])
