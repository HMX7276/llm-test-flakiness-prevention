"""Validate provider-specific parameters on real task prompts outside pilot v0."""
import json
from pathlib import Path
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.api_client import complete
from runner.prepare import save
from runner.evaluate import evaluate
from analysis.format_sensitivity import unwrap


if __name__=='__main__':
    frozen=json.loads((ROOT/'runs/pilot_v0/schedule.json').read_text())
    for model,extra in [('qwen3.5',{'enable_thinking':False}),('deepseek-v4-flash',{'thinking':False})]:
        cell=next(c for c in frozen['cells'] if c['model_id']==model and c['context_condition']=='risk' and c['method']=='B0')
        dest=ROOT/'runs/api_calibration'/('code_'+model)
        if (dest/'record.json').exists():
            continue
        payload={'model':model,'messages':[{'role':'user','content':cell['prompt']}],
                 'temperature':0.7,'top_p':1,'max_tokens':512,'max_length':512,
                 'chat_template_kwargs':extra,'stream':False}
        save(dest/'request.json',payload)
        started=datetime.now(timezone.utc).isoformat()
        response,attempts=complete(payload,timeout=60,retries=0)
        record={'purpose':'Configuration calibration, excluded from pilot v0','started_utc':started,'attempts':attempts,
                'response':response,'evaluation':None}
        if response:
            content=response.get('choices',[{}])[0].get('message',{}).get('content') or ''
            (dest/'content.txt').write_text(content,encoding='utf-8')
            (dest/'test_calibration.py').write_text(unwrap(content),encoding='utf-8')
            record['evaluation']=evaluate(dest/'test_calibration.py',dest/'evaluation',frozen['config'])
        save(dest/'record.json',record)
        print(model,'success' if response else 'failed',response.get('usage') if response else None,
              record['evaluation'],flush=True)
