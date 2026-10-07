"""Expose only the presampled original artifacts, never model/method outcomes."""
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runner.lean_followup_v1 import RUN, verified
from runner.prepare import save


def main():
    s = verified()
    dest = ROOT / 'review/semantic_lean_v1'
    if (dest / 'mapping_private.json').exists():
        raise SystemExit('Review packet already frozen; refusing to replace it.')
    assert all((RUN / 'outputs' / c['output_id'] / 'record.json').exists() for c in s['cells']), 'Generation not finished.'
    selected = set(s['human_sampling_draft']['output_ids'])
    assert len(selected) == 48
    tasks = {t['task_id']: t for t in s['tasks']}
    available, unavailable = [], []
    for c in s['cells']:
        if c['output_id'] not in selected:
            continue
        out = RUN / 'outputs' / c['output_id']
        record = json.loads((out / 'record.json').read_text(encoding='utf-8'))
        code = out / 'test_generated.py'
        if record['status'] != 'api_success' or not code.exists():
            unavailable.append({'private_output': c['output_id'], 'reason': 'no_returned_test_artifact'})
            continue
        codehash = hashlib.sha256(code.read_bytes()).hexdigest()
        assert codehash == record['code_sha256']
        t = tasks[c['task_id']]
        available.append({'private_run': RUN.name, 'private_output': c['output_id'],
                          'target': t['target'], 'contract': t['contract'], 'source': t['target_source'],
                          'code': code.read_text(encoding='utf-8'), 'code_sha256': codehash,
                          'code_path': code.relative_to(ROOT).as_posix()})
    random.Random(20261008).shuffle(available)
    mapping = [{'review_id': f'L{i:03d}', **row} for i, row in enumerate(available, 1)]
    public = [{k: v for k, v in row.items() if k not in ['private_run', 'private_output', 'code_path']} for row in mapping]
    save(dest / 'mapping_private.json', mapping)
    save(dest / 'unavailable_private.json', unavailable)
    save(dest / 'human_review_blank.json', {'schema': 'semantic-review-lean-v1', 'reviewer': '', 'reviewer_type': 'human',
          'items': [{'review_id': r['review_id'], 'code_sha256': r['code_sha256'], 'correctness': '',
                     'robustness': '', 'adequacy': '', 'reason': ''} for r in public]})
    template = (ROOT / 'review/review_template.html').read_text(encoding='utf-8')
    html = template.replace('semantic-review-v1', 'semantic-review-lean-v1').replace('llm-semantic-v1-human', 'llm-semantic-lean-v1-human')
    html = html.replace('human_semantic_review.json', 'human_semantic_review_lean_v1.json')
    html = html.replace('测试语义核验', f'测试语义核验 · 精简重复比较 {len(public)} 项')
    html = html.replace('__REVIEW_DATA__', json.dumps(public, ensure_ascii=False).replace('<', '\\u003c'))
    (dest / '人工语义核验.html').write_text(html, encoding='utf-8')
    (dest / '使用说明.txt').write_text(
        f'本包来自生成前抽定的 48 个单元，其中可评审 {len(public)} 项、未返回 {len(unavailable)} 项。未按成功或运行结果补选。\n'
        '请核验未修改的原代码：正确性、稳健性、充分性，分别给判断和理由。不确定可保留。\n'
        '模型、方法、执行结果和 AI 判断隐藏；代码风格仍可能带来线索。只对这批审查样本报告人工结果。\n'
        '本包用独立 L 编号和保存键，不覆盖之前核验。导出 human_semantic_review_lean_v1.json 后交回。\n', encoding='utf-8')
    print(f'Frozen blinded review packet: {len(public)} available, {len(unavailable)} unavailable from 48 presampled cells.')


if __name__ == '__main__':
    main()
