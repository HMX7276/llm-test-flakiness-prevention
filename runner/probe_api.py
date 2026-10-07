"""Small configuration diagnostics, excluded from experiment outcomes."""
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.api_client import complete
from runner.prepare import save


if __name__=='__main__':
    variants=[('qwen_enable_thinking_false',{'enable_thinking':False}),
              ('qwen_template_thinking_false',{'chat_template_kwargs':{'enable_thinking':False}})]
    for name,extra in variants:
        dest=ROOT/'runs/api_calibration'/name
        if (dest/'record.json').exists():
            continue
        payload={'model':'qwen3.5','messages':[{'role':'user','content':'Reply with exactly OK.'}],
                 'max_tokens':64,'temperature':0.7,'stream':False,**extra}
        save(dest/'request.json',payload)
        start=datetime.now(timezone.utc).isoformat()
        response,attempts=complete(payload,timeout=30,retries=0)
        save(dest/'record.json',{'purpose':'API calibration; excluded from pilot outcomes','started_utc':start,
                                'attempts':attempts,'response':response})
        print(name,'success' if response else 'failed',attempts,
              response.get('usage') if response else None,flush=True)
