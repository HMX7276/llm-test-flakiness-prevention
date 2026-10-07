"""Credential stays in memory; no credential-bearing request/error serialization."""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://uni-api.cstcloud.cn/v1"


def complete(payload, timeout=90, retries=2):
    text = (ROOT / "api-key.txt").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^KEY1:\s*(\S+)", text)
    if not match:
        raise ValueError("Missing KEY1 credential")
    secret = match.group(1)
    attempts = []
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            BASE_URL + "/chat/completions", data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"})
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            raw = raw.replace(secret, "[REDACTED]")
            result = json.loads(raw)
            attempts.append({"attempt": attempt, "status": "ok", "latency": time.monotonic()-start})
            return result, attempts
        except urllib.error.HTTPError as exc:
            # Retain a bounded, redacted diagnostic body; no request headers.
            error_body = exc.read(4096).decode('utf-8',errors='replace').replace(secret,'[REDACTED]')
            error_body = re.sub(r'(?i)Bearer\s+\S+','Bearer [REDACTED]',error_body)
            attempts.append({"attempt": attempt, "status": "http_error", "http_status": exc.code,
                             "latency": time.monotonic()-start,"error_body":error_body})
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            attempts.append({"attempt": attempt, "status": "transport_or_parse_error",
                             "error_type": type(exc).__name__, "latency": time.monotonic()-start})
        if attempt < retries:
            time.sleep(2 ** attempt)
    return None, attempts
