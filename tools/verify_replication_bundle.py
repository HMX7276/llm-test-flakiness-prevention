"""Read-only verification of a staged replication bundle; no API access."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    return json.loads((ROOT/p).read_text(encoding='utf-8'))


def main():
    manifest = load('MANIFEST.json')
    for name, expected in manifest['sha256'].items():
        p = ROOT/name
        assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == expected, name
    for filename, fields in [('runs/lean_followup_v1/schedule.json', ['source_sha256','snapshot_sha256']),
                             ('runs/independent_validation_v1/frozen.json', ['hashes'])]:
        frozen = load(filename)
        for field in fields:
            for name, expected in frozen[field].items():
                assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    schedule=load('runs/lean_followup_v1/schedule.json')
    outcomes=Counter()
    for cell in schedule['cells']:
        folder='runs/lean_followup_v1/outputs/'+cell['output_id']
        record=load(folder+'/record.json')
        assert record['status']=='api_success'
        assert hashlib.sha256((ROOT/folder/'test_generated.py').read_bytes()).hexdigest()==record['code_sha256']
        outcomes[load(folder+'/evaluation/summary.json')['status']]+=1
    assert len(schedule['cells'])==72 and outcomes['stable_proxy_valid']==32
    supplement=load('runs/lean_followup_v1/reviewed_execution/summary.json')
    assert len(supplement['rows'])==15
    assert sum(r['outcome']['status']=='stable_proxy_valid' for r in supplement['rows'])==14
    independent=load('analysis/independent_validation_v1_summary.json')
    assert independent['completed']==189 and independent['method_abstentions']==3
    for group in independent['groups']:
        records=[json.loads(p.read_text(encoding='utf-8')) for p in
                 (ROOT/'runs/independent_validation_v1/executions'/group['task']/group['variant']).glob('*/record.json')]
        assert len(records)==group['completed']
        assert dict(Counter(r['status'] for r in records))==group['counts']
    assert not any(p.name.lower()=='api-key.txt' for p in ROOT.rglob('*') if p.is_file())
    print(f"PASS: {len(manifest['sha256'])} file hashes; frozen dependencies; 72 primary generations; 15 reviewed outputs; 189 external diagnostic runs. No API calls.")


if __name__=='__main__':main()
