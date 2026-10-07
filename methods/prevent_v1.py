"""Conservative v1: prove direct receiver provenance, otherwise abstain.

No inference from clean examples. Randomness/time rules await semantic validation.
The v0 implementation remains unchanged for reproducibility.
"""
import ast
from methods.prevent import transform as legacy_transform

def transform(source, example, contract):
    if contract.get('target')!='penman.graph.Graph.variables':
        return example,{'changed':False,'reason':'unsupported_risk_abstain'}
    try:
        tree=ast.parse(example)
    except SyntaxError:
        return example,{'changed':False,'reason':'invalid_context'}
    imported=any(isinstance(n,ast.ImportFrom) and n.module=='penman' and
        any(a.name=='Graph' and a.asname is None for a in n.names) for n in tree.body)
    if not imported:
        return example,{'changed':False,'reason':'unproven_import'}
    # Narrow straight-line test only. Reject aliases, rebinding, branches, shadowing.
    tests=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
    if len(tests)!=1 or tests[0].args.args or tests[0].decorator_list:
        return example,{'changed':False,'reason':'unsupported_scope'}
    body=tests[0].body
    if any(not isinstance(n,(ast.Assign,ast.Assert)) for n in body):
        return example,{'changed':False,'reason':'unsupported_control_flow'}
    bound={}
    receivers=set()
    for statement in body:
        if isinstance(statement,ast.Assign):
            if len(statement.targets)!=1 or not isinstance(statement.targets[0],ast.Name):
                return example,{'changed':False,'reason':'unsupported_assignment'}
            name=statement.targets[0].id
            if name in bound or name in {'Graph','list','Counter'}:
                return example,{'changed':False,'reason':'rebinding_or_shadowing'}
            value=statement.value
            bound[name]=isinstance(value,ast.Call) and isinstance(value.func,ast.Name) and value.func.id=='Graph'
        for n in ast.walk(statement):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='variables':
                if not isinstance(n.func.value,ast.Name) or not bound.get(n.func.value.id):
                    return example,{'changed':False,'reason':'unproven_receiver'}
                receivers.add(n.func.value.id)
    # Reject top-level assignments/classes/helper functions which could shadow imports/builtins.
    if any(not isinstance(n,(ast.ImportFrom,ast.FunctionDef)) for n in tree.body):
        return example,{'changed':False,'reason':'unsupported_module_scope'}
    if any(n is not tests[0] and (n.module!='penman' or any(a.name!='Graph' or a.asname for a in n.names))
           for n in tree.body if isinstance(n,ast.ImportFrom)):
        return example,{'changed':False,'reason':'unsupported_import'}
    result,evidence=legacy_transform(source,example)
    evidence['receiver_provenance']=sorted(receivers)
    evidence['version']='v1_direct_import_and_constructor_only'
    return result,evidence
