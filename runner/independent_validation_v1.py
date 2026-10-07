"""Freeze and run three external applicability probes; never alters M v2."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RUN = ROOT/'runs/independent_validation_v1'
DATA = ROOT/'data/independent_validation_v1'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    if (RUN/'frozen.json').exists():
        raise RuntimeError('Already frozen; use run/summary instead.')
    import networkx as nx
    import cachetools
    from faker.providers import BaseProvider
    from methods.prevent_v2 import transform
    selection = json.loads((DATA/'selection.json').read_text(encoding='utf-8'))
    for p, h in selection['method_sha256'].items():
        assert sha(ROOT/p) == h
    for name, version in selection['candidate_versions'].items():
        assert importlib.metadata.version(name) == version
    examples = [
        dict(id='networkx_ancestors', package='networkx', target='networkx.algorithms.dag:ancestors',
             source=inspect.getsource(nx.ancestors), contract=dict(risk_type='unordered_collection', target='networkx.algorithms.dag.ancestors'),
             risk="from networkx import DiGraph, ancestors\ndef test_ancestors():\n    g = DiGraph([('a', 'c'), ('b', 'c')])\n    assert list(ancestors(g, 'c')) == ['a', 'b']\n",
             reference="from networkx import DiGraph, ancestors\ndef test_ancestors():\n    g = DiGraph([('a', 'c'), ('b', 'c')])\n    assert ancestors(g, 'c') == {'a', 'b'}\n",
             mutation=dict(file='networkx/algorithms/dag.py', before='return {child for parent, child in nx.bfs_edges(G, source, reverse=True)}', after='return set()', name='omit_ancestors'),
             source_url='https://networkx.org/documentation/networkx-3.4.2/reference/algorithms/generated/networkx.algorithms.dag.ancestors.html'),
        dict(id='cachetools_ttl', package='cachetools', target='cachetools:TTLCache.__getitem__',
             source=inspect.getsource(cachetools.TTLCache), contract=dict(risk_type='time', clock_semantics='synchronous_elapsed_duration', clock_dependency='time', target_module='cachetools'),
             risk="import time\nfrom cachetools import TTLCache\ndef test_expiration():\n    cache = TTLCache(maxsize=2, ttl=0.04)\n    cache['a'] = 1\n    time.sleep(0.02)\n    assert cache['a'] == 1\n    time.sleep(0.03)\n    assert 'a' not in cache\n",
             reference="from cachetools import TTLCache\ndef test_expiration():\n    clock = [0.0]\n    cache = TTLCache(maxsize=2, ttl=0.04, timer=lambda: clock[0])\n    cache['a'] = 1\n    clock[0] += 0.02\n    assert cache['a'] == 1\n    clock[0] += 0.03\n    assert 'a' not in cache\n",
             mutation=dict(file='cachetools/__init__.py', before='return self.timer() < link.expires', after='return True', name='membership_ignores_expiration'),
             source_url='https://cachetools.readthedocs.io/en/v5.5.2/'),
        dict(id='faker_random_int', package='faker', target='faker.providers:BaseProvider.random_int',
             source=inspect.getsource(BaseProvider.random_int), contract=dict(risk_type='randomness', random_semantics='seeded_example_regression', rng_dependency='random', target_module='faker.providers', target_qualname='BaseProvider.random_int'),
             risk="from faker import Faker\nFaker.seed(0)\ndef test_seeded_integer():\n    fake = Faker('en_US')\n    assert fake.random_int(min=0, max=9999) == 6311\n",
             reference="from faker import Faker\ndef test_seeded_integer():\n    fake = Faker('en_US')\n    fake.seed_instance(0)\n    assert fake.random_int(min=0, max=9999) == 6311\n",
             mutation=dict(file='faker/providers/__init__.py', before='return self.generator.random.randrange(min, max + 1, step)', after='return min', name='always_minimum'),
             source_url='https://faker.readthedocs.io/en/master/#seeding-the-generator')]
    for task in examples:
        folder = DATA/task['id']; folder.mkdir(parents=True, exist_ok=True)
        task['provenance'] = 'assistant-constructed diagnostic, not an upstream historical flaky test'
        task['human_semantic_review'] = 'not yet obtained for this new pair'
        for key in ['risk', 'reference', 'source']:
            (folder/(key+'.py')).write_text(task.pop(key), encoding='utf-8')
        transformed, evidence = transform((folder/'source.py').read_text(encoding='utf-8'), (folder/'risk.py').read_text(encoding='utf-8'), task['contract'])
        (folder/'method_output.py').write_text(transformed, encoding='utf-8')
        task['method_result'] = evidence
        task['output_equals_risk'] = transformed == (folder/'risk.py').read_text(encoding='utf-8')
        package = importlib.import_module(task['package'])
        src = Path(package.__file__).parent
        dest = RUN/'projects'/task['id']/task['package']
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        mutant = RUN/'mutants'/task['id']
        shutil.copytree(dest, mutant/task['package'])
        mp = mutant/task['mutation']['file']; code = mp.read_text(encoding='utf-8')
        assert code.count(task['mutation']['before']) == 1, task['id']
        mp.write_text(code.replace(task['mutation']['before'],task['mutation']['after']), encoding='utf-8')
        save(folder/'task.json', task)
    files = list(DATA.rglob('*.py')) + list(DATA.rglob('*.json'))
    files += [p for sub in ['projects','mutants'] for p in (RUN/sub).rglob('*') if p.is_file()]
    files += [ROOT/'runner/independent_trace_v1.py', Path(__file__), ROOT/'notes/independent_validation_v1_protocol.txt', ROOT/'configs/requirements-independent-v1.lock.txt']
    files += [ROOT/p for p in selection['method_sha256']]
    frozen = dict(date='2026-10-07', kind='external_applicability_diagnostics_not_llm_comparison', tasks=examples,
                  planned_primary_executions=180, planned_diagnostic_executions=9, python=sys.version,
                  hashes={p.relative_to(ROOT).as_posix():sha(p) for p in files})
    save(RUN/'frozen.json', frozen)
    (RUN/'frozen.sha256').write_text(sha(RUN/'frozen.json')+'\n', encoding='ascii')
    print('Frozen 3 external probes, 6 examples, 3 diagnostic mutations before execution.', flush=True)


def verify():
    assert sha(RUN/'frozen.json') == (RUN/'frozen.sha256').read_text().strip()
    frozen = json.loads((RUN/'frozen.json').read_text(encoding='utf-8'))
    for p,h in frozen['hashes'].items():
        assert sha(ROOT/p) == h, p
    return frozen


def run_one(task, variant, seed):
    dest = RUN/'executions'/task['id']/variant/f'{seed:02d}'
    if (dest/'record.json').exists():
        return json.loads((dest/'record.json').read_text(encoding='utf-8'))
    dest.mkdir(parents=True, exist_ok=True)
    code = DATA/task['id']/('reference.py' if variant=='mutant' else variant+'.py')
    shutil.copyfile(code,dest/'test_subject.py')
    project = RUN/('mutants' if variant=='mutant' else 'projects')/task['id']
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
    env.update(PATH=str(Path(sys.executable).parent), PYTHONPATH=os.pathsep.join([str(project),str(ROOT/'runner')]),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONHASHSEED=str(seed),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',
        TEMP=str(dest),TMP=str(dest),VALIDATION_TARGET=task['target'],VALIDATION_SEED=str(seed),VALIDATION_TRACE=str(dest/'trace.json'))
    start=time.monotonic()
    try:
        proc=subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider','-p','independent_trace_v1',str(dest/'test_subject.py')],cwd=dest,env=env,capture_output=True,timeout=30)
        (dest/'stdout.txt').write_bytes(proc.stdout);(dest/'stderr.txt').write_bytes(proc.stderr)
        trace=json.loads((dest/'trace.json').read_text(encoding='utf-8')) if (dest/'trace.json').exists() else {}
        phases=trace.get('reports',[])
        if trace.get('collection_errors'): status='collection_failure'
        elif any(r['when']!='call' and r['outcome']=='failed' for r in phases):status='setup_teardown_error'
        elif any(r['outcome']=='skipped' for r in phases):status='skip'
        elif any(r['when']=='call' and r['outcome']=='failed' for r in phases):status='fail'
        elif proc.returncode==0 and trace.get('collected')==1 and trace.get('target_calls',0)>0:status='pass'
        else:status='infrastructure_or_target_error'
        result=dict(task=task['id'],variant=variant,seed=seed,status=status,returncode=proc.returncode,target_calls=trace.get('target_calls',0))
    except subprocess.TimeoutExpired:
        result=dict(task=task['id'],variant=variant,seed=seed,status='timeout',target_calls=0)
    result.update(code_sha256=sha(code),seconds=time.monotonic()-start)
    save(dest/'record.json',result)
    return result


def summarize(frozen):
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((RUN/'executions').rglob('record.json'))]
    groups=[]
    for task in frozen['tasks']:
        for variant,n in [('risk',30),('reference',30),('mutant',3)]:
            selected=[r for r in rows if r['task']==task['id'] and r['variant']==variant]
            groups.append(dict(task=task['id'],variant=variant,planned=n,completed=len(selected),counts=dict(Counter(r['status'] for r in selected)),all_target_called=bool(selected) and all(r['target_calls']>0 for r in selected)))
    report=dict(scope=frozen['kind'],completed=len(rows),planned=189,method_abstentions=sum(not t['method_result']['changed'] for t in frozen['tasks']),groups=groups,
                no_llm_calls=True,human_semantic_review='not obtained for new pairs',frozen_sha256=sha(RUN/'frozen.json'))
    save(ROOT/'analysis/independent_validation_v1_summary.json',report)
    lines=['新项目适用性诊断（不是 LLM 独立效果比较）',f"完成 {len(rows)}/189 次执行；冻结 M v2 拒绝转换 {report['method_abstentions']}/3。",'任务 | 版本 | 已完成/计划 | 结果 | 均调用真实目标']
    lines += [f"{g['task']} | {g['variant']} | {g['completed']}/{g['planned']} | {g['counts']} | {g['all_target_called']}" for g in groups]
    lines += ['三个项目为规则开发后目的性选择的新项目，构造示例不是历史自然风险。','reference 为助手编写的人工参考，不是 M 输出，未获本批人工语义核验。','mutant 为每项目一项固定手工缺陷，仅作断言诊断，不是正式变异得分。','对三个目标全弃权时，M 与原例相同，因此未进行没有干预差异的 LLM 生成比较。','时钟例包含受控延迟；30/30 通过不能证明绝无不稳定性；运行次数不等于独立项目数。']
    (ROOT/'analysis/independent_validation_v1_report.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','run','summary']);args=parser.parse_args()
    if args.phase=='prepare':prepare()
    else:
        frozen=verify()
        if args.phase=='run':
            with ThreadPoolExecutor(max_workers=3) as pool:
                jobs=[pool.submit(run_one,t,v,s) for t in frozen['tasks'] for v,n in [('risk',30),('reference',30),('mutant',3)] for s in range(n)]
                for i,j in enumerate(jobs,1):
                    j.result()
                    if i%30==0:print('Completed',i,'/189',flush=True)
        summarize(frozen)
