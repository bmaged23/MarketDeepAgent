# MarketDeepAgent

**[GitHub source, demo and complete project README](https://github.com/bmaged23/MarketDeepAgent)**

An AI grocery marketplace with retrieval, cart and customer agents, hybrid product search, persistent conversations and explicitly confirmed orders. The portable CPU image includes the seeded catalog and pinned BGE embedding weights; the main LLM runs on your Ollama Cloud account.

## Docker setup

The tested public image is [bmaged23/market-deep-agent](https://hub.docker.com/r/bmaged23/market-deep-agent). The complete evaluation, publication and public pull/smoke checks passed on 23 October 2026; exact commit and digest are in [release evidence](https://github.com/bmaged23/MarketDeepAgent/blob/main/docs/RELEASE_VERIFICATION.md).

The Linux amd64 CPU image contains the FastAPI application, storefront assets, seeded 100-product catalog, indexing tools, SQLite migrations and pinned BGE model weights. It contains no API keys, user database or private evaluation traces. A fresh model download and repository clone are not required. BGE's upstream model card declares MIT licensing and its README is included with the pinned weights.

### Two files, then run

```bash
mkdir market-deep-agent
cd market-deep-agent
curl -fL https://raw.githubusercontent.com/bmaged23/MarketDeepAgent/main/docker-compose.yml -o docker-compose.yml
curl -fL https://raw.githubusercontent.com/bmaged23/MarketDeepAgent/main/.env.example -o .env
```

Edit `.env` to set `OLLAMA_API_KEY`, an accessible `OLLAMA_MODEL` and optionally `ADMIN_API_KEY` for administration. You supply your own cloud account; the 120B LLM is not bundled or hosted locally.

```bash
docker pull bmaged23/market-deep-agent:cpu
docker compose up -d
docker compose logs -f market
```

Open http://localhost:8600 and register/sign in. API docs: http://localhost:8600/docs. Startup waits for Qdrant, initializes only an empty SQL catalog, reconciles/indexes vectors, releases provisioning model memory and starts the server and synchronization watcher. Initial indexing may take time on CPU. Compose explicitly sets container paths, CPU device and internal Qdrant address.

`/healthz` is process liveness. `/readyz` checks actual local embeddings, catalog size and vector count. Neither endpoint guarantees that the cloud key can access the selected model; real agent evaluations test that separately.

### Data, updates and cleanup

Named volumes hold `/app/storage` and Qdrant storage. Bundled seed assets stay in the image so updates do not mount an old copy of source code over them. A nonempty catalog is preserved on restart; it is not silently reset to the seed.

```bash
docker compose down
# Upgrade without deleting volumes:
docker compose pull
docker compose up -d
```

Only use `docker compose down -v` when intentionally erasing accounts, carts, orders, conversations and vectors. The tests use uniquely named disposable resources, not your regular Qdrant instance.

### CPU and GPU

The public portable image uses CPU embeddings and needs no NVIDIA hardware. Native CUDA 12.4 inference and resource comparison are verified separately. A GPU build stage is included for future verification but no tested public GPU image is claimed. Allow at least 8 GB available RAM and 8 GB free disk as an initial CPU budget; runtime peaks depend on concurrent model processes. Native Windows/macOS/ARM behavior is not universally certified.

For source development,`docker/compose.storage.yml` starts only Qdrant on localhost:6335. The root `docker-compose.yml` runs the complete packaged application. See the main README for native GPU setup.

### Container verification

```bash
python -m scripts.release.smoke_image --image bmaged23/market-deep-agent:cpu
```

This creates a separate network, SQL volume and Qdrant container. It checks real inference/search, UI/API routes, signup/session/CSRF, cart totals, quote-only stock preservation, confirmed cash-on-delivery checkout, idempotent retry, exact stock deduction and persistence across replacement containers. It removes only its own resources. It is distinct from the 100-case live-agent evaluation.

### Troubleshooting

- Start Docker Desktop/Engine and enable Linux containers. For WSL integration errors, verify the daemon first; never delete VHDX files or use factory reset as a routine fix.
- Check real C-drive capacity on Windows. WSL's large virtual free-space number does not guarantee Windows can grow its disk. Low disk can interrupt image exports.
- If port8600 is busy, edit only the host port in Compose.
- Inspect startup logs when readiness is503. Do not claim a healthy process has a complete index.
- Provider authentication/model errors require a valid account-accessible model/key; the image does not buy credits.
- Use the internal Qdrant address in Compose; container localhost does not point at the host service.

## Agent, SQL and answer evaluation

### References precede execution

`evaluation/datasets/market-agents-v1.jsonl` freezes 100 synthetic scenarios, with a seeded catalog snapshot and SHA-256 manifest. Its coverage is 30 retrieval, 25 cart, 25 coordinator and 20 six-turn journeys. Retrieval labels reuse the first 30 source-labelled starter queries transparently; extra relevant alternatives may not be exhaustively labelled. Workflow variants and journeys are mechanically authored from catalog facts, not generated from the model's output. The set is exposed regression data, not an untouched generalization benchmark or human-adjudicated real shoppers.

Reference evidence contains **stable product IDs plus frozen facts**. Constraints are separate structured fields. Qdrant point IDs equal SQL product IDs; runtime labels such as `chunk_0` are not the reference identity. Cart/coordinator cases include initial synthetic state, expected decisions and forbidden changes. Journeys share the same conversation and cart across six actual turns, including corrections, then explicit confirmation and retry/ownership checks.

### SQL is evaluated as behavior

The agent produces validated structured catalog selections, not arbitrary SQL text. We inspect actual tool arguments, fields/filters, returned product IDs and values, SQL selection metadata and pagination. Catalog facts and frozen `oracle_sql`/parameters independently identify reference evidence. Extra results must satisfy requested price/category/stock constraints. Equivalent valid SQL/hybrid plans are accepted; an exact SQL string or identical tool sequence is not required.

SQL remains authoritative for current product facts. Cart actions must preserve stock until trusted form confirmation. Confirmed orders must deduct stock once, belong to the authenticated customer and survive a repeated submission without duplication. Existing offline tests also cover SQL injection-like strings, ownership, stale revisions and transactional behavior. These are distinct from live LLM decisions.

### Deterministic scores

- Direct hybrid top5 ranking: recall (relevant IDs found / labelled relevant IDs), precision (hits/5), reciprocal rank and binary nDCG against the ideal relevance ranking.
- Retrieval agent: requested IDs, approved-only evidence, facts matching SQL, filters, search budget, completion and SQL pagination.
- Cart: correct action, exact quantities, no unconfirmed orders/stock deduction, quote readiness and delivered-review behavior.
- Coordinator: specialist selection, retrieval before new-product writes, source evidence, reply contract and keeping confirmation tokens outside answer-model input.
- Journeys: per-turn product/cart/state checks plus total, quote, explicit confirmation, idempotence, customer isolation and stock deduction.

A scenario passes only if every required check passes. Report each agent's pass rate separately. A completed request is not automatically a correctness pass; exceptions and missing checks remain failures.

### Independent answer assessments

Agents use `gpt-oss:120b` on Ollama Cloud. `gemma4:31b` judges 145 coordinator/journey replies with two separate calls each:

1. **Correctness/completeness/relevance:** question, actual answer and frozen catalog/expected-state references. Judge only facts/actions requested by that question, not every field in the reference.
2. **Faithfulness:** question, actual answer and actual tool evidence; no reference answer is supplied. Unsupported factual/action claims are recorded explicitly.

Each rubric score is an integer 0–4, normalized by dividing by 4. Report means and coverage per metric; there is no combined overall answer score. These judgments need human calibration and cannot independently certify truth. Correctness and faithfulness are different: an answer can accurately repeat incomplete evidence while failing to answer the question.

The parser accepts exact JSON code fences but enforces required fields, score ranges and schema. Only invalid responses or transient requests get bounded repair/retry (maximum 3 judge attempts). Valid low scores are never retried. Earlier failed tooling attempts are kept privately and are not counted as successful judgments. Monetary cost is not inferred without billing rates.

### Baseline and candidate are separate

The original native-GPU source baseline completed100 cases and passed91: retrieval27/30,cart23/25,coordinator23/25,journeys18/20. Its direct-ranking recall/MRR/nDCG@5 were1.0 on30 known starter queries; precision@5 was0.2467. Answer means over 145 replies: correctness0.8879,completeness0.9172,relevance0.9517,faithfulness0.9483. These narrow results do not establish universal accuracy.

Observed failures informed changes to original-request preservation, owned review context, quote-only routing and focused retrieval planning. Baseline outputs remain unchanged under ignored `.evaluation-local/source-baseline`; public aggregates are in `evaluation/results/`. The full release evaluation runs **inside the exact candidate image**, using an isolated100-product catalog and its own Qdrant volume, not the host source checkout or existing customer data.

### Release policy

`evaluation/release-policy.json` requires100 completed unique cases, expected per-agent coverage, no unscored execution errors, candidate image identity and145 scored answers/290 valid judge calls. Per-agent floors are0.87/0.89/0.89/0.87 and maximum absolute regression from baseline is0.03. Answer floors are correctness/completeness0.80,relevance0.85,faithfulness0.90.

Critical checkout/idempotence/ownership/stock checks must be present and pass for every journey; forbidden early mutations or confirmation-token leakage block release independently of averages. These are operational thresholds declared before the full candidate run, not statistical significance limits. Missing data cannot silently count as success.

### Run and inspect

```bash
python -m pip install -r requirements/evaluation.txt
# Add CPU/GPU runtime dependencies for native inference when needed.
python -m scripts.evaluation.run_suite --output .evaluation-local/source-run
# Actual image, own disposable SQL/Qdrant, cloud key from environment or ignored .env:
python -m scripts.release.evaluate_image --image market-deep-agent:candidate-cpu --output .evaluation-local/candidate
python -m scripts.evaluation.judge_answers --input .evaluation-local/candidate/cases.jsonl --output .evaluation-local/candidate/judge
python -m scripts.evaluation.check_gate --candidate .evaluation-local/candidate
```

`--resume` on native execution/judging retains every complete result, including valid low scores, and executes only missing IDs. Do not combine outputs from different code/model/reference versions under one experiment. Raw traces contain synthetic checkout tokens and stay ignored. Only sanitized aggregate artifacts are public.

LangSmith stores frozen examples, per-agent/tool traces and feedback. Inference still happens through Ollama Cloud or local BGE; LangSmith is the experiment store, not the model host. Legacy exports without timestamps are explicitly replay-labelled; actual measured durations are retained separately. New captures include real UTC timestamps. Credentials, token fields and synthetic address fields are excluded from export payloads where structured.


### Intermediate candidate finding

The first full CPU-image candidate passed 97/100: retrieval 30/30, cart 25/25, coordinator 25/25, journeys 17/20. Its journey score 0.85 was below the declared 0.87 floor, so it was rejected. The three failures were multi-product SQL lookups without name/ID selectors. A new server-side resolver uses literal catalog names (not evaluation labels) to fill missing SQL selectors; targeted reruns of those three journeys passed. The subsequent complete image evaluation passed 100/100 and the unchanged gate, as recorded below. Earlier candidate results remain in `evaluation/results/candidate-iteration1.json`; targeted checks do not replace the benchmark.

Long-term preference-memory proposals are not enabled in these live journeys; conversation history is exercised, while owner/version/deletion memory guards have separate offline tests. Do not claim complete live long-term-memory quality from this set.


### Resource and failure audit

New runs capture worker CPU/RAM and, on native CUDA, sampled whole-device VRAM/utilization. Per-case observations describe the shared worker while that case runs; parallel cases overlap and cannot be charged individual resource ownership. Summary peaks include model startup and exclude the browser, Qdrant and cloud servers. These are sampled observations, not continuous peak guarantees.

Release gating also checks raw judge IDs, schema-valid score coverage and aggregate arithmetic rather than trusting summary counters alone. Failed-but-completed runs are exported to LangSmith even when the gate blocks publication. SQL projections may omit eligibility fields; constraints are checked against frozen SQL facts while any contradictory returned facts still fail.

Cart/coordinator counts include paraphrase variants of 12 and 10 underlying operation templates; they are not 25 independent behavior types or independent statistical trials. The 20 journeys use different product pairs. This coverage remains narrower than real shopper traffic.

### Verified released candidate — 23 October 2026

Both the released Docker CPU image and native GPU workflow run passed **100/100**: retrieval 30/30, cart 25/25, coordinator 25/25 and journeys 20/20. The released image passed every required critical check and the unchanged quality policy. Its application fingerprint matches the native GPU run.

| Released CPU answer metric | Normalized mean | Coverage |
|---|---:|---:|
| Correctness | 90.34% | 145/145 replies |
| Completeness | 93.10% | 145/145 replies |
| Relevance | 95.00% | 145/145 replies |
| Faithfulness | 95.69% | 145/145 replies |

All **290/290** rubric judgments were valid. These are normalized judge means, not percentages of conversations passed. Baseline means were correctness 88.79%, completeness 91.72%, relevance 95.17% and faithfulness 94.83%; relevance did not improve. No statistical significance or held-out generalization is claimed. The earlier 97/100 CPU candidate and interrupted vector-service failure remain retained separately; neither substitutes for final release evidence.

The released CPU experiment is `market-image-39986061885-1` in LangSmith; 100 root case IDs were independently checked against the frozen dataset after export. [Public release record](https://github.com/bmaged23/MarketDeepAgent/blob/main/docs/RELEASE_VERIFICATION.md), [CPU summary](https://github.com/bmaged23/MarketDeepAgent/blob/main/evaluation/results/docker-cpu-final.json), [answer scores](https://github.com/bmaged23/MarketDeepAgent/blob/main/evaluation/results/docker-answer-judgments.json), [GPU summary](https://github.com/bmaged23/MarketDeepAgent/blob/main/evaluation/results/native-gpu-final.json).

## Performance measurements

![CPU/GPU embeddings](https://raw.githubusercontent.com/bmaged23/MarketDeepAgent/main/docs/performance/embedding-comparison.svg)

### Same-query CPU/GPU comparison

| Configuration | Warm median | Warm p95 | Queries/s | Peak RAM | Peak CUDA allocation | Mean CPU* |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPU · batch 1 | 231.53 ms | 290.12 ms | 4.27 | 1586.7 MiB | — | 197.6% |
| GPU · batch 1 | 23.87 ms | 41.51 ms | 36.82 | 1964.5 MiB | 1288.9 MiB | 100.7% |
| GPU · batch 8 | 6.48 ms | 8.25 ms | 147.17 | 1936.3 MiB | 1293.6 MiB | 106.2% |

GPU single-query warm median was **9.70× faster** in this benchmark. CPU/GPU cosine agreement exceeded 0.99999988 (float32 rounding can report 1.0). Batch 8 timing is amortized; it excludes waiting to accumulate a batch and is not individual-user latency.

*CPU 100% means one occupied logical core. RSS and whole-device GPU observations are sampled; device metrics include other processes. Each process warmed the same 20 queries repeated 3 times, with a separate startup query. Peak RAM includes model initialization. GPU allocation/reservation comes from PyTorch. These are worker measurements, not whole-stack requirements.

### Agent/cloud bottleneck

The 100-case source GPU baseline recorded **607 LLM calls**. Their summed durations accounted for **98.6%** of summed per-case elapsed time, including network/provider wait. Cases overlap across2 workers, so these sums are not experiment wall time. Recorded usage: **1,523,226 input tokens**, **182,161 output tokens**; usage is available on 607/607 calls. No invoice/currency cost is inferred.

The main gpt-oss:120b model is hosted on Ollama Cloud. Local GPU resources are used for BGE, not for a 120B local model. The public portable image uses CPU embeddings; the native CUDA setup is measured separately. GPU embedding speedup is not an equal whole-agent speedup.

### Implementation changes and limits

- BGE weights are pinned and bundled in the candidate image, avoiding a first-run model download.
- Provisioning runs in a short-lived process so its model memory is released before the server starts. The existing per-process model cache avoids repeated loads.
- Current user cart instructions are retained across delegation; owned SQL delivery status avoids unnecessary review clarification. Explicit quote preparation does not authorize checkout.
- Controlled embedding benchmarks and final CPU/GPU workflow measurements are complete. The published container uses CPU; native GPU support is verified separately. No GPU-container or universal compatibility claim.

### Reproduce

```bash
python -m scripts.performance.benchmark_embeddings --device cpu --batch-size 1 --output .release-local/performance/cpu-batch1
# Run these with the CUDA environment:
python -m scripts.performance.benchmark_embeddings --device cuda --batch-size 1 --output .release-local/performance/cuda-batch1
python -m scripts.performance.benchmark_embeddings --device cuda --batch-size 8 --output .release-local/performance/cuda-batch8
python -m scripts.performance.build_report
```

[Machine-readable measurements](https://github.com/bmaged23/MarketDeepAgent/blob/main/docs/performance/measurements.json). Raw vectors and full agent traces stay ignored.

### Final release measurements — 23 October 2026

The exact released CPU image and native CUDA application each passed all **100/100** workflows on the same frozen dataset and application fingerprint. GPU workflows were evaluated separately; the 145-answer rubric evaluation in [the evaluation report](https://github.com/bmaged23/MarketDeepAgent/blob/main/docs/EVALUATION.md) belongs to the released CPU image.

| Scope | Cases | Docker CPU median | Native GPU median | CPU passed | GPU passed |
|---|---:|---:|---:|---:|---:|
| Retrieval specialist | 30 | 14.52 s | 18.68 s | 30/30 | 30/30 |
| Cart specialist | 25 | 3.08 s | 3.88 s | 25/25 | 25/25 |
| Customer coordinator | 25 | 17.43 s | 14.87 s | 25/25 | 25/25 |
| Complete six-turn journey | 20 | 87.02 s | 76.91 s | 20/20 | 20/20 |

A journey includes six actual requests plus deterministic confirmation/ownership/retry checks. Native GPU median across its **120 individual journey turns** was **13.19 s**. These are two-worker regression runs, not a controlled CPU/GPU end-to-end speed comparison: GitHub CPU and local GPU hardware differ, provider load varies, and the cloud judge overlapped part of the native run. Use the controlled embedding benchmark above for the GPU speedup claim.

| Resource observation | Docker CPU worker | Native GPU worker |
|---|---:|---:|
| Peak worker RSS, including startup | 2068.0 MiB | 2029.2 MiB |
| Mean process CPU, one logical core = 100% | 4.02% | 2.44% |
| Observed whole-device peak VRAM | Not sampled | 1463 MiB |
| Observed whole-device peak GPU utilization | Not sampled | 30% |

These averages include cloud/network waiting, which explains low mean CPU utilization; they are not peak compute demand. Worker RSS excludes Qdrant/browser/cloud services. GPU samples include other device users and are not per-agent allocation. Per-case shared-worker samples and intermediate traces remain in the private raw experiment. The interrupted Qdrant-down attempt was preserved and excluded from this healthy run.

[Released CPU aggregate](https://github.com/bmaged23/MarketDeepAgent/blob/main/evaluation/results/docker-cpu-final.json) · [Native GPU aggregate](https://github.com/bmaged23/MarketDeepAgent/blob/main/evaluation/results/native-gpu-final.json) · [Release verification](https://github.com/bmaged23/MarketDeepAgent/blob/main/docs/RELEASE_VERIFICATION.md)
