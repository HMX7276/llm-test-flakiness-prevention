import ast
import hashlib
import json
import os
import random
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from methods.prevent import transform


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp,path)


def main():
    cfg = json.loads((ROOT / "configs/pilot_v0.json").read_text())
    project = ROOT / "vendor" / ("penman-" + cfg["commit"])
    graph = (project / "penman/graph.py").read_text(encoding="utf-8")
    cls = next(n for n in ast.parse(graph).body if isinstance(n, ast.ClassDef) and n.name == "Graph")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "variables")
    source = textwrap.dedent("\n".join(graph.splitlines()[fn.lineno-1:fn.end_lineno]))
    example = "from penman import Graph\n\ndef test_example():\n    g = Graph([('a', ':instance', 'alpha'), ('b', ':instance', 'beta')])\n    assert list(g.variables()) == ['a', 'b']\n"
    clean = example.replace("list(g.variables()) == ['a', 'b']", "g.variables() == {'a', 'b'}")
    task = {**{k:cfg[k] for k in ("task_id", "project_id", "commit", "dataset_layer")},
            "risk_type":"unordered_collection", "target":"penman.graph.Graph.variables",
            "target_source":source, "graph_module_sha256":hashlib.sha256(graph.encode()).hexdigest(),
            "contract":"Graph(triples=None, top=None) accepts iterable (source, role, target) triples. variables() returns the set of source identifiers and, if provided, the explicit top. The return is a set. Import Graph from penman.",
            "risk_example":example, "clean_example":clean,
            "provenance":"Real fixed project; constructed order-sensitive example inspired by tests/test_graph.py::TestGraph::test_variables. Not a historical flaky-test pair.",
            "human_review_status":"pending"}
    save(ROOT / "data/tasks/penman_variables.json", task)
    for condition, code in (("risk",example),("clean",clean)):
        (ROOT / f"data/tasks/test_example_{condition}.py").write_text(code, encoding="utf-8")
    cleaned, evidence = transform(source, example)
    (ROOT / "data/tasks/test_example_transformed.py").write_text(cleaned, encoding="utf-8")
    save(ROOT / "data/tasks/transformation.json", evidence)
    base = (ROOT / "prompts/base.txt").read_text()
    warning = (ROOT / "prompts/warning.txt").read_text()
    rng = random.Random(cfg["schedule_seed"])
    schedule = []
    for generation_round in range(1, cfg["generation_rounds"]+1):
        cells = [(model,ctx,method) for model in cfg["models"] for ctx in cfg["contexts"] for method in cfg["methods"]]
        rng.shuffle(cells)
        for model, condition, method in cells:
            shown = example if condition == "risk" else clean
            evidence = {"changed":False}
            extra = warning if method == "B1" else ""
            if method == "M":
                shown, evidence = transform(source, shown)
                if evidence["changed"]:
                    extra = "The example was normalized using the target's set-valued contract. Check complete contents without relying on iteration order."
            prompt = f"{base}\n{extra}\nContract:\n{task['contract']}\nTarget source:\n{source}\nExample:\n{shown}"
            output_id = f"g{len(schedule)+1:03d}"
            schedule.append({"output_id":output_id,"model_id":model,"context_condition":condition,
                             "method":method,"generation_round":generation_round,"prompt":prompt,
                             "prompt_hash":hashlib.sha256(prompt.encode()).hexdigest(),"transformation":evidence})
    path = ROOT / "runs/pilot_v0/schedule.json"
    if path.exists():
        raise SystemExit("Refusing to overwrite an existing frozen schedule")
    save(path, {"config":cfg,"task":task,"cells":schedule})
    print("Prepared",len(schedule),"cells; no API calls made")


if __name__ == "__main__":
    main()
