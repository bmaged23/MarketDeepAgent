# Repository organization

The repository separates the running application, reproducible environments, frozen evaluation references, public results and local generated data.

| Location | Responsibility |
|---|---|
| `app/` | FastAPI application grouped by business feature: authentication, catalog, search, indexing, carts, orders, conversations and customer memory. |
| `app/agents/{customer,retrieval,cart}/` | Each agent owns its implementation, tools, schemas, prompts and feature-specific evaluation commands. Customer coordinates the specialists. |
| `app/model_clients/` | Cloud LLM and local embedding adapters. |
| `app/database/migrations/` | Ordered SQL schema migrations. |
| `app/utils/` | Shared helpers used across features. |
| `UI/frontend/` | Storefront HTML, CSS and browser JavaScript. |
| `UI/backend/` | Compatibility entry point; its requirements file forwards to the maintained root dependency entry point. |
| `data/` | Catalog seeding and documented nutrition/pricing inputs. Generated databases and model downloads are ignored. |
| `products/images/` | Product images required by the seed catalog and demo. |
| `requirements/` | Pinned CPU, GPU, development and evaluation locks, plus `.in` maintainer inputs. These are separate environments, not duplicate installations. |
| `evaluation/datasets/` | Frozen questions, catalog facts, expected actions and manifest fingerprints. |
| `evaluation/results/` | Public aggregate baseline, candidate and release evidence. Historical failures remain visible as evidence. |
| `scripts/evaluation/` | Frozen-suite execution, answer judging, quality gate and LangSmith export. |
| `scripts/performance/` | Embedding benchmarking and reproducible report generation. |
| `scripts/release/` | Candidate-image evaluation, isolated container checks and gated publication. |
| `scripts/runtime/` | Container provisioning and application startup. |
| `docker/` | Dockerfile, model provisioning and storage-only development Compose file. Root Compose starts the complete packaged application. |
| `tests/` | Python tests grouped by feature, plus frontend behavior tests. |
| `docs/guides/` | Setup, evaluation, performance, CI/CD, release evidence and this organization guide. |
| `docs/dockerhub/` | Docker Hub Overview and its generator. |
| `docs/performance/` | Published benchmark JSON and charts. |
| `docs/assets/` | Published demo, preview and generated diagrams. |
| `docs/` website files | GitHub Pages entry points, browser assets, recording and diagram tools. These remain alongside the website they maintain. |
| `.github/workflows/` | Offline verification and the gated image-release pipeline. |

## Root entry points

Use `README.md` first. `requirements.txt` selects the CPU runtime; `requirements-dev.txt` selects offline testing. `pyproject.toml` defines package metadata. `.env.example` documents configuration without credentials. `docker-compose.yml` runs the published application and Qdrant. `.gitignore` and `.dockerignore` define publication boundaries.

## Files that stay local

- `.env`: credentials and local configuration.
- `.venv*`, `.cache/`, `.uv-cache/`, `node_modules/`: environments and downloaded tooling.
- `data/model_cache/`, SQLite database/sidecar files and Qdrant storage: generated runtime data.
- `.evaluation-local/`: full model/tool traces, failed attempts and raw measurements.
- `.release-local/`: release logs, temporary helpers, private configuration and archived environment snapshots.
- `description/`: local assistant handover.
- `storage/`, `artifacts/`, `outputs/`, `logs/`, test reports and profiler output: disposable generated files.
- Intermediate video conversions and raw recordings: local until a validated demo replaces the published asset.

Published metrics, frozen references, model prompts, dependency locks, product images and the working demo remain tracked. An ignore rule does not remove an already tracked file; obsolete tracked material must be explicitly moved out of the published tree.
