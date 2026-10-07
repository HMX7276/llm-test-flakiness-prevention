# Preserving Test Effectiveness When Preventing Flakiness Transfer

Research code and evidence for an exploratory study of example preprocessing in
large language model test generation. This is a development study, not a claim
of demonstrated superiority or a published journal article.

## Start here

- `methods/`: preprocessing implementation.
- `runner/`, `configs/`, `prompts/`: experimental orchestration and settings.
- `analysis/`: result aggregation and comparison audits.
- `artifacts/replication_code_data_v1.0.0.zip`: complete prepared evidence bundle with original
  requests, generated tests, execution results, human labels, adjudications,
  source snapshots, third-party notices and a hash manifest.

The ZIP is the reproducible execution workspace. The source folders here are for
browsing; scripts depending on data must be run from the extracted ZIP. Extract
the ZIP into a **separate new directory**, change into it, and run with Python 3.11:

```text
python tools/verify_replication_bundle.py
python analysis/audit_gate_comparison_v1.py
```

Neither command calls a model or requires an API key. See `README.txt` inside the
ZIP for pinned dependencies and a clean-directory six-execution smoke check.
This repository distributes code and experimental data only. Manuscript drafts,
paper-specific author metadata and paper source files are excluded. `CITATION.cff`
identifies the artifact creators for attribution. The original experimental
records are unchanged. Version 1.0.0 is archived at
[Zenodo, DOI 10.5281/zenodo.23209519](https://doi.org/10.5281/zenodo.23209519).
Zenodo uses TAR.XZ compression and GitHub uses ZIP; all 53,495 archive members
are byte-identical, including the hash manifest. See `CITATION.cff` for citation.

## What the data represent

The development registry has six projects: PENMAN, Tale, lithoxyl, RandomFileTree,
fishbase and compare-mt. It contains historical-test adaptations and constructed
risk cases, not six uniformly evaluated independent benchmarks. Compare-mt has
a manual reference and was not scheduled for LLM generation.

The frozen follow-up contains 72 generations on three already-seen targets,
two API model aliases, four methods and three generations per cell. Execution
repeats are not independent tasks. Original and post-hoc execution-gate results
remain separate; gate differences limit method comparisons. Human-review
archives cover 144 artifacts across separate batches, not overlapping double
annotation. Hand-seeded defects are synthetic diagnostics, not historical bugs.

Three additional projects (NetworkX, cachetools, Faker) contribute 189 executions
of applicability diagnostics. The frozen method abstained on all three; manually
written references are not automatic-method outputs. These probes are not an
independent LLM effectiveness comparison.

No model training or private institutional business dataset is part of this
study. Original upstream code is attributed to its projects and versions.

## Credentials, support and licensing

No API key is distributed. New model calls require the replicator's own access;
recorded-data verification does not. Known keys were scanned before packaging,
and all packaged files have a SHA-256 manifest. The code/data archive was
derived from the previously verified local evidence bundle.

This research received no specific grant from any funding agency in the public,
commercial, or not-for-profit sectors. We acknowledge the large language model
API platform of China Science and Technology Cloud for free API access.

Original research software is licensed under **MIT**; original research data
is licensed under **CC BY 4.0**, within the authors' rights. These are separate
component licenses, not blanket relicensing of the archive. See
`LICENSE_NOTICE.txt`, `LICENSES/`, and the bundle's third-party notices.
Third-party source and embedded excerpts retain their original terms.
Earlier lithoxyl full-source reproduction requires pinned upstream retrieval,
as explained in the bundle. The archive is not a fully offline reproduction of
every historical development environment.
