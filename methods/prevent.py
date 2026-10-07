"""Narrow development prototype; reads source and example, never clean oracle."""
import ast
import copy
import difflib


def transform(source: str, example: str):
    target = ast.parse(source).body[0]
    annotation = ast.unparse(target.returns) if target.returns else ""
    doc = ast.get_docstring(target) or ""
    # Conservative scope: known set-valued target with explicit public contract.
    if not annotation.startswith("Set[") or "set of" not in doc.lower():
        return example, {"changed": False, "reason": "unsupported_contract"}
    tree = ast.parse(example)
    changes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        cmp = node.test
        if not (isinstance(cmp, ast.Compare) and len(cmp.ops) == 1
                and isinstance(cmp.ops[0], ast.Eq) and isinstance(cmp.left, ast.Call)
                and isinstance(cmp.left.func, ast.Name) and cmp.left.func.id == "list"
                and len(cmp.left.args) == 1 and not cmp.left.keywords
                and isinstance(cmp.comparators[0], ast.List)):
            continue
        call = cmp.left.args[0]
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == target.name and not call.args and not call.keywords):
            continue
        # Preserve expected multiplicities; do not silently deduplicate literals.
        try:
            values = ast.literal_eval(cmp.comparators[0])
            if not all(isinstance(v, str) for v in values):
                continue
        except (ValueError, TypeError):
            continue
        cmp.left = ast.Call(func=ast.Name(id="Counter", ctx=ast.Load()),
                            args=[copy.deepcopy(call)], keywords=[])
        cmp.comparators[0] = ast.Call(func=ast.Name(id="Counter", ctx=ast.Load()),
                                     args=[cmp.comparators[0]], keywords=[])
        changes.append({"line": node.lineno, "rule": "set_contract_order_assertion",
                        "reason": "Set-valued API has no iteration-order guarantee; compare full multiplicities."})
    if not changes:
        return example, {"changed": False, "reason": "no_supported_risk"}
    tree.body.insert(0, ast.ImportFrom(module="collections", names=[ast.alias(name="Counter")], level=0))
    result = ast.unparse(ast.fix_missing_locations(tree)) + "\n"
    return result, {"changed": True, "changes": changes,
                    "diff": "".join(difflib.unified_diff(example.splitlines(True), result.splitlines(True)))}
