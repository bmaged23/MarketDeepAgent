# Project scripts

Run modules from the repository root.

- `evaluation/build_dataset.py`: author/freeze source-first references; explicit maintainer operation, not a release-time regeneration.
- `evaluation/run_suite.py`: execute all frozen agent scenarios and record intermediate model/tool outputs locally.
- `runtime/serve.py`: initialize an empty seeded catalog, index pending products, then serve FastAPI/UI with the indexing watcher.
- `performance/`: reserved for measured CPU/GPU and application benchmarks.

Application feature CLIs remain beside their services under `app/` (indexing, memory, existing specialist evaluations). Private recordings, traces, credentials and temporary outputs belong in ignored `.evaluation-local/` or `.release-local/`, never sibling project folders.
