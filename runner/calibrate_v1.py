"""Independent, resumable model parameter diagnostics, excluded from experiments."""
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.api_client import complete
from runner.prepare import save

def main():
    base=ROOT/'runs/api_calibration_v1'
    models={'qwen3.5':{'enable_thinking':False},'deepseek-v4-flash':{'thinking':False}}
    for model,extra in models.items():
        for field in ['max_tokens','max_length','both']:
            dest=base/model/field
            if (dest/'record.json').exists():
                continue
            payload={'model':model,'messages':[{'role':'user','content':
                'Write the integers from 1 to 300, one number per line. Do not explain or abbreviate.'}],
                'temperature':0,'top_p':1,'stream':False,'chat_template_kwargs':extra}
            for key in (['max_tokens','max_length'] if field=='both' else [field]):
                payload[key]=32
            save(dest/'request.json',payload)
            started=datetime.now(timezone.utc).isoformat()
            response,attempts=complete(payload,timeout=60,retries=0)
            save(dest/'record.json',{'purpose':'length/config diagnostic only','started_utc':started,
                 'attempts':attempts,'response':response})
            print(model,field,'success' if response else 'failed',
                  response.get('usage') if response else attempts,flush=True)
if __name__=='__main__':
    main()
