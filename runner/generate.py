import argparse
import concurrent.futures
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.api_client import complete
from runner.prepare import save


def generate_cells(limit, offset=0, span=None):
    run = ROOT / "runs/pilot_v0"
    frozen = json.loads((run / "schedule.json").read_text(encoding="utf-8"))
    cfg = frozen["config"]
    count = 0
    end = min(cfg["max_generation_requests"], offset+span) if span is not None else cfg["max_generation_requests"]
    for cell in frozen["cells"][offset:end]:
        dest = run / "outputs" / cell["output_id"]
        if (dest / "record.json").exists():
            continue
        if count >= limit:
            break
        dest.mkdir(parents=True, exist_ok=True)
        payload = {"model":cell["model_id"],"messages":[{"role":"user","content":cell["prompt"]}],
                   "temperature":cfg["temperature"],"top_p":cfg["top_p"],"max_tokens":cfg["max_tokens"],"stream":False}
        save(dest / "request.json", payload)
        (dest / "prompt.txt").write_text(cell["prompt"],encoding="utf-8")
        start = datetime.now(timezone.utc).isoformat()
        result, attempts = complete(payload,cfg["request_timeout_seconds"],cfg["max_transport_retries"])
        record = {**cell, **{k:cfg[k] for k in ("task_id","project_id","commit","dataset_layer","temperature","top_p","max_tokens")},
                  "started_utc":start,"attempts":attempts,"retry_count":len(attempts)-1,
                  "seed":None,"model_revision":None,"python":platform.python_version(),
                  "raw_output_path":str((dest / "response.json").relative_to(ROOT)),
                  "status":"api_success" if result else "api_incomplete"}
        if result:
            save(dest / "response.json",result)
            record["usage"] = result.get("usage",{})
            record["returned_model"] = result.get("model")
            record["system_fingerprint"] = result.get("system_fingerprint")
            choices = result.get("choices",[])
            content = choices[0].get("message",{}).get("content") if choices else None
            record["finish_reason"] = choices[0].get("finish_reason") if choices else None
            content = content if isinstance(content,str) else ""
            (dest / "content.txt").write_text(content,encoding="utf-8")
            fences = re.findall(r"```(?:python)?\s*\n(.*?)```",content,re.S)
            code = fences[0] if len(fences)==1 else content.strip()
            (dest / "test_generated.py").write_text(code+"\n",encoding="utf-8")
            record["code_sha256"] = hashlib.sha256((dest / "test_generated.py").read_bytes()).hexdigest()
            record["content_chars"] = len(content)
        save(dest / "record.json",record)
        print(cell["output_id"],cell["model_id"],cell["method"],record["status"],record.get("finish_reason"),record.get("usage",{}),flush=True)
        count += 1
        if not result:
            print("Stopping batch after infrastructure failure; record preserved",flush=True)
            break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--workers", type=int, choices=[1,2], default=1)
    args = parser.parse_args()
    if args.workers == 1:
        generate_cells(args.limit,args.offset)
    else:
        # Low concurrency; each worker owns exactly one saved schedule cell.
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(generate_cells,1,i,1) for i in range(args.offset,args.offset+args.limit)]
            for job in jobs:
                job.result()


if __name__ == "__main__":
    main()
