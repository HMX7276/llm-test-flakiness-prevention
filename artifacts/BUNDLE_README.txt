Code and data replication bundle v1 - 7 October 2026

Scope
This local bundle contains study code, recorded model requests/responses, generated tests,
execution traces, diagnostic defects, human-review records and adjudications, source
snapshots for the frozen core comparison, and the three new external applicability probes.
It is prepared for public release but has not been uploaded and has no archive DOI.
Paper entry points: paper/manuscript_v5.pdf and paper/manuscript_zh_review_v5.pdf.

Quick offline verification (Python 3.11; standard library only; no API key)
  python tools/verify_replication_bundle.py
This checks all packaged hashes, frozen source snapshots, 72 generation records,
all 15 gate-reviewed outputs and all 189 new diagnostic executions.

Recompute the gate comparison (no API)
  python analysis/audit_gate_comparison_v1.py

Clean-directory execution check
  python -m venv .venv-replay
  .venv-replay/Scripts/python -m pip install -r configs/requirements-independent-v1.lock.txt
  .venv-replay/Scripts/python tools/replay_independent.py --destination ../replay-smoke --smoke
On Unix use .venv-replay/bin/python. Omit --smoke for all 189 executions; always
choose a new destination. Six smoke executions validate three passing references
and three failing mutants; they do not repeat the full statistical observation.

Original 72-generation comparison
Use Python 3.11 and configs/requirements-dev-v2.lock.txt. The frozen schedule,
source hashes, model aliases, prompts and raw outputs are in runs/lean_followup_v1.
  python -m runner.lean_followup_v1 verify
Existing evaluate/generate commands resume saved outputs rather than replacing them.
Generating new outputs is a new stochastic replication, not reconstruction of the
original outputs. It needs the experimenter's own institutional API access; no
credential is included. The public endpoint and model aliases may change.

Evidence boundaries
Three new projects were purposively chosen after adapter development. M abstained
on all three. The reference tests are assistant-authored, not M outputs and not
independently human-reviewed. The 189 runs are applicability diagnostics, not a
new model-comparison experiment. Primary counts (32 stable; 31 detecting a defect)
and post-hoc additions (14 stable; all 14 detecting a defect) remain separate.

Packaging exclusions
Virtual environments, caches, API credentials, downloaded literature/archives in
data/sources, old PDFs and duplicated upstream-baseline project worktrees are omitted.
The original logs and aggregate results are retained. Historical absolute paths in
logs describe the original machine; they are not portable execution instructions.
Lithoxyl's old source snapshot lacks its referenced LICENSE file, so that full
vendor tree and raw library copies are not redistributed here. Recover the exact
commit 9961553a065a1ad8bb7a2407fe74f2cfd6c79a20 from https://github.com/mahmoud/lithoxyl
to reproduce that earlier development-only task. This does not affect the frozen
72-generation comparison or three external probes. Target excerpts in task records
remain for interpreting the experiments.

Licensing and attribution
Third-party source notices remain with vendor sources; installed probe package
licenses are also copied to THIRD_PARTY. Original research code/data have not yet
been assigned a distribution license by the authors. This archive does not change
third-party license terms or imply that the authors own the included projects.
See notes/related_work_verification_v2.json for literature sources.
