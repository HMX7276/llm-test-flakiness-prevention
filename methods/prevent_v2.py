"""Auditable narrow rules: logical elapsed time and test-local RNG dependency.

Neither rule reads a clean example, observed outcomes, or mutant results.
Contracts are source-backed declarations, not model guesses. Unsupported examples
are retained exactly. This is not a claim of unrestricted semantic equivalence.
"""
import ast
import difflib
from methods.prevent_v1 import transform as set_transform

def unchanged(code,reason):
    return code,{'changed':False,'reason':reason,'version':'v2'}

def fingerprint_assertions(tree):
    return [ast.dump(n,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.Assert)]

def finish(before,tree,rule,details):
    out=ast.unparse(ast.fix_missing_locations(tree))+'\n'
    preserved=fingerprint_assertions(ast.parse(before))==fingerprint_assertions(ast.parse(out))
    assert preserved, 'Rules must not modify/remove assertions'
    return out,{'changed':True,'version':'v2','rule':rule,'assertions_ast_preserved':True,
        **details,'diff':''.join(difflib.unified_diff(before.splitlines(True),out.splitlines(True)))}

def transform(source,example,contract):
    if contract.get('risk_type')=='unordered_collection':
        return set_transform(source,example,contract)
    try: tree=ast.parse(example)
    except SyntaxError: return unchanged(example,'invalid_context')
    fns=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
    if len(fns)!=1 or not fns[0].name.startswith('test_'):
        return unchanged(example,'requires_one_plain_test')
    fn=fns[0]
    if fn.decorator_list or fn.args.args or fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg:
        return unchanged(example,'fixtures_or_decorators_require_review')
    if any(isinstance(n,(ast.Try,ast.With,ast.While,ast.AsyncFunctionDef,ast.ClassDef)) for n in ast.walk(tree)):
        return unchanged(example,'unsupported_control_flow')
    if any(isinstance(n,ast.Name) and n.id.startswith('_risk_') for n in ast.walk(tree)):
        return unchanged(example,'reserved_name_collision')
    if any(isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store) and n.id in {'time','random','monkeypatch'} for n in ast.walk(tree)):
        return unchanged(example,'dependency_shadowing')
    kind=contract.get('risk_type')
    if kind=='time':
        return logical_clock(source,example,tree,fn,contract)
    if kind=='randomness':
        return local_rng(source,example,tree,fn,contract)
    return unchanged(example,'unsupported_contract')

def logical_clock(source,example,tree,fn,contract):
    # A source-backed seam, no wall-date/expiry/performance/asynchronous claims.
    if contract.get('clock_semantics')!='synchronous_elapsed_duration' or contract.get('clock_dependency')!='time':
        return unchanged(example,'unproven_elapsed_time_contract')
    if contract.get('target_module')!='tale.pubsub':
        return unchanged(example,'unvalidated_clock_adapter')
    if 'return time.time() - self.last_event' not in source or 'self.last_event = time.time()' not in source:
        return unchanged(example,'clock_source_evidence_missing')
    if any(not isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef)) for n in tree.body):
        return unchanged(example,'module_side_effects')
    if not any(isinstance(n,ast.Import) and any(a.name=='time' and not a.asname for a in n.names) for n in tree.body):
        return unchanged(example,'clock_import_not_proven')
    valid_import=any(isinstance(n,ast.ImportFrom) and n.module=='tale.pubsub' and
                     all(a.name=='topic' and not a.asname for a in n.names) for n in tree.body)
    if not valid_import: return unchanged(example,'constructor_import_not_proven')
    allowed_imports={'time','tale.pubsub'}
    for node in tree.body:
        if isinstance(node,ast.Import) and any(a.name not in allowed_imports or a.asname for a in node.names):
            return unchanged(example,'unsupported_import')
        if isinstance(node,ast.ImportFrom) and node.module!='tale.pubsub':
            return unchanged(example,'unsupported_import')
    receivers=set(); sleeps=[]
    for node in fn.body:
        if isinstance(node,ast.Assign):
            if len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name): return unchanged(example,'unsupported_assignment')
            name=node.targets[0].id
            if name in receivers or name=='topic': return unchanged(example,'receiver_rebinding')
            if not (isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='topic'):
                return unchanged(example,'clock_reads_or_other_assignments')
            receivers.add(name)
        elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            call=node.value
            if isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=='time' and call.func.attr=='sleep':
                if len(call.args)!=1 or call.keywords: return unchanged(example,'dynamic_sleep')
                try: duration=ast.literal_eval(call.args[0])
                except (ValueError,TypeError): return unchanged(example,'dynamic_sleep')
                if type(duration) not in (float,int) or not 0<=duration<=3600: return unchanged(example,'unsupported_sleep_duration')
                sleeps.append((node,duration))
            elif not (isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id in receivers and call.func.attr=='send'):
                return unchanged(example,'non_elapsed_operations')
        elif isinstance(node,ast.Assert):
            if any(isinstance(n,ast.Call) for n in ast.walk(node)): return unchanged(example,'assertion_calls_require_review')
            attrs=[n for n in ast.walk(node) if isinstance(n,ast.Attribute)]
            if not attrs or any(n.attr!='idle_time' or not isinstance(n.value,ast.Name) or n.value.id not in receivers for n in attrs):
                return unchanged(example,'non_duration_assertion')
        else: return unchanged(example,'unsupported_statement')
    if not receivers or not sleeps: return unchanged(example,'no_supported_time_risk')
    fn.args.args.append(ast.arg(arg='monkeypatch'))
    prefix=ast.parse("import tale.pubsub as _risk_module\nfrom types import SimpleNamespace as _risk_namespace\n").body
    setup=ast.parse("_risk_clock = [0.0]\nmonkeypatch.setattr(_risk_module, 'time', _risk_namespace(time=lambda: _risk_clock[0]))\n").body
    for node,duration in sleeps:
        replacement=ast.parse(f'_risk_clock[0] += {duration!r}').body[0]
        fn.body[fn.body.index(node)]=replacement
    fn.body=setup+fn.body
    tree.body=prefix+tree.body
    return finish(example,tree,'logical_elapsed_clock',{'dependency':'tale.pubsub.time','base':0.0,
        'sleep_replacements':len(sleeps),'limitation':'Tests logical duration/reset semantics, not OS scheduling or timer accuracy.'})

def local_rng(source,example,tree,fn,contract):
    if contract.get('random_semantics')!='seeded_example_regression' or contract.get('rng_dependency')!='random':
        return unchanged(example,'statistical_or_unproven_random_oracle')
    module=contract.get('target_module')
    if module not in {'randomfiletree.core','fishbase.fish_random'}:
        return unchanged(example,'unvalidated_rng_adapter')
    target=contract['target_qualname']
    if '.' in target or not all(f'random.{name}' in source for name in ['randint']):
        return unchanged(example,'rng_source_evidence_missing')
    seeds=[]
    for n in tree.body:
        if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and ast.unparse(n.value.func)=='random.seed': seeds.append(n)
        elif not isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef)):
            return unchanged(example,'module_side_effects')
    if len(seeds)!=1 or len(seeds[0].value.args)!=1 or seeds[0].value.keywords:
        return unchanged(example,'requires_existing_explicit_seed')
    try: seed=ast.literal_eval(seeds[0].value.args[0])
    except (TypeError,ValueError): return unchanged(example,'nonliteral_seed')
    if type(seed)!=int: return unchanged(example,'noninteger_seed')
    if not any(isinstance(n,ast.Import) and any(a.name=='random' and not a.asname for a in n.names) for n in tree.body):
        return unchanged(example,'rng_import_not_proven')
    if not any(isinstance(n,ast.ImportFrom) and n.module==module and any(a.name==target and not a.asname for a in n.names) for n in tree.body):
        return unchanged(example,'target_import_not_proven')
    for n in tree.body:
        if isinstance(n,ast.Import) and any(a.name!='random' or a.asname for a in n.names): return unchanged(example,'unsupported_import')
        if isinstance(n,ast.ImportFrom) and (n.module!=module or any(a.name!=target or a.asname for a in n.names)):
            return unchanged(example,'unsupported_import')
    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call)]
    if len(calls)!=1 or not isinstance(calls[0].func,ast.Name) or calls[0].func.id!=target:
        return unchanged(example,'requires_single_direct_rng_target_call')
    if any(isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store) and n.id==target for n in ast.walk(fn)):
        return unchanged(example,'target_shadowing')
    if any(not isinstance(n,ast.Assert) for n in fn.body): return unchanged(example,'requires_direct_assertion')
    fn.args.args.append(ast.arg(arg='monkeypatch'))
    tree.body.remove(seeds[0])
    tree.body.insert(0,ast.Import(names=[ast.alias(name=module,asname='_risk_module')]))
    fn.body=ast.parse(f"monkeypatch.setattr(_risk_module, 'random', random.Random({seed!r}))").body+fn.body
    return finish(example,tree,'local_rng_dependency',{'dependency':module+'.random','seed_from_example':seed,
        'seed_search':False,'limitation':'Preserves seeded regression case, not the breadth of a distributional test; Python RNG version dependent.'})
