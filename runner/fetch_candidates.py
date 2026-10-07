"""Fetch immutable public candidate snapshots; never executes downloaded code."""
import concurrent.futures
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runner.prepare import save

def fetch(c):
    name=c['project'].split('/')[-1]
    url=f"https://codeload.github.com/{c['project']}/zip/{c['commit']}"
    archive=ROOT/'data/sources'/f"{name}_{c['commit']}.zip"
    if not archive.exists():
        with urllib.request.urlopen(url,timeout=90) as r:
            archive.write_bytes(r.read())
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            path=(ROOT/'vendor'/entry.filename).resolve()
            if not path.is_relative_to((ROOT/'vendor').resolve()):
                raise ValueError('Unsafe archive member')
        z.extractall(ROOT/'vendor')
    result={**c,'archive_url':url,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'project_path':f"vendor/{name}-{c['commit']}"}
    save(ROOT/'data/sources'/f'{name}_provenance.json',result)
    return name

if __name__=='__main__':
    names=set(sys.argv[1:] or ['kanren','configaro','lithoxyl','RandomFileTree','Tale'])
    candidates=json.loads((ROOT/'data/candidate_pool.json').read_text(encoding='utf-8'))['shortlist']
    chosen={c['project']:c for c in candidates if c['project'].split('/')[-1] in names}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for name in pool.map(fetch,chosen.values()):
            print(name,'downloaded',flush=True)
