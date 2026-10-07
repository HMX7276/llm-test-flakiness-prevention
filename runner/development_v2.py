"""Reuse recorded generation/execution mechanics with a distinct frozen run root."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import runner.development_v1 as engine
engine.RUN=ROOT/'runs/development_v2'
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='controls':
        import json
        from runner.evaluate import evaluate
        schedule=json.loads((engine.RUN/'schedule.json').read_text(encoding='utf-8'))
        for task in schedule['tasks']:
            for condition in ['risk','clean','transformed']:
                source=ROOT/'data/development_v2'/task['task_id']/(condition+'.py')
                dest=engine.RUN/'validated_controls'/task['task_id']/condition
                result=evaluate(source,dest,engine.config(task),workers=3)
                print(task['task_id'],condition,result['status'],result['counts'],flush=True)
    else:
        engine.main()
