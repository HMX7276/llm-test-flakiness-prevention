"""Record the actual imported target module for upstream/mutant attribution."""
import hashlib
import json
import os
from pathlib import Path
import sys


def pytest_sessionfinish(session, exitstatus):
    name = os.environ['BASELINE_MODULE']
    module = sys.modules.get(name)
    path = Path(module.__file__).resolve() if module is not None else None
    Path(os.environ['BASELINE_ORIGIN_FILE']).write_text(json.dumps({
        'module': name, 'path': str(path) if path else None,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path else None,
    }), encoding='utf-8')
