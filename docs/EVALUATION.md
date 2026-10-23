# Agent, SQL and answer evaluation

## References precede execution

`evaluation/datasets/market-agents-v1.jsonl` freezes 100 synthetic scenarios, with a seeded catalog snapshot and SHA-256 manifest. Its coverage is 30 retrieval, 25 cart, 25 coordinator and 20 six-turn journeys. Retrieval labels reuse the first 30 source-labelled starter queries transparently; extra relevant alternatives may not be exhaustively labelled. Workflow variants and journeys are mechanically authored from catalog facts, not generated from the model's output. The set is exposed regression data, not an untouched generalization benchmark or human-adjudicated real shoppers.

Reference evidence contains **stable product IDs plus frozen facts**. Constraints are separate structured fields. Qdrant point IDs equal SQL product IDs; runtime labels such as `chunk_0` are not the reference identity. Cart/coordinator cases include initial synthetic state, expected decisions and forbidden changes. Journeys share the same conversation and cart across six actual turns, including corrections, then explicit confirmation and retry/ownership checks.

## SQL is evaluated as behavior

The agent produces validated structured catalog selections, not arbitrary SQL text. We inspect actual tool arguments, fields/filters, returned product IDs and values, SQL selection metadata and pagination. Catalog facts and frozen `oracle_sql`/parameters independently identify reference evidence. Extra results must satisfy requested price/category/stock constraints. Equivalent valid SQL/hybrid plans are accepted; an exact SQL string or identical tool sequence is not required.

SQL remains authoritative for current product facts. Cart actions must preserve stock until trusted form confirmation. Confirmed orders must deduct stock once, belong to the authenticated customer and survive a repeated submission without duplication. Existing offline tests also cover SQL injection-like strings, ownership, stale revisions and transactional behavior. These are distinct from live LLM decisions.

## Deterministic scores

- Direct hybrid top5 ranking: recall (relevant IDs found / labelled relevant IDs), precision (hits/5), reciprocal rank and binary nDCG against the ideal relevance ranking.
- Retrieval agent: requested IDs, approved-only evidence, facts matching SQL, filters, search budget, completion and SQL pagination.
- Cart: correct action, exact quantities, no unconfirmed orders/stock deduction, quote readiness and delivered-review behavior.
- Coordinator: specialist selection, retrieval before new-product writes, source evidence, reply contract and keeping confirmation tokens outside answer-model input.
- Journeys: per-turn product/cart/state checks plus total, quote, explicit confirmation, idempotence, customer isolation and stock deduction.

A scenario passes only if every required check passes. Report each agent's pass rate separately. A completed request is not automatically a correctness pass; exceptions and missing checks remain failures.

## Independent answer assessments

Agents use `gpt-oss:120b` on Ollama Cloud. `gemma4:31b` judges 145 coordinator/journey replies with two separate calls each:

1. **Correctness/completeness/relevance:** question, actual answer and frozen catalog/expected-state references. Judge only facts/actions requested by that question, not every field in the reference.
2. **Faithfulness:** question, actual answer and actual tool evidence; no reference answer is supplied. Unsupported factual/action claims are recorded explicitly.

Each rubric score is an integer 0–4, normalized by dividing by 4. Report means and coverage per metric; there is no combined overall answer score. These judgments need human calibration and cannot independently certify truth. Correctness and faithfulness are different: an answer can accurately repeat incomplete evidence while failing to answer the question.

The parser accepts exact JSON code fences but enforces required fields, score ranges and schema. Only invalid responses or transient requests get bounded repair/retry (maximum 3 judge attempts). Valid low scores are never retried. Earlier failed tooling attempts are kept privately and are not counted as successful judgments. Monetary cost is not inferred without billing rates.

## Baseline and candidate are separate

The original native-GPU source baseline completed100 cases and passed91: retrieval27/30,cart23/25,coordinator23/25,journeys18/20. Its direct-ranking recall/MRR/nDCG@5 were1.0 on30 known starter queries; precision@5 was0.2467. Answer means over 145 replies: correctness0.8879,completeness0.9172,relevance0.9517,faithfulness0.9483. These narrow results do not establish universal accuracy.

Observed failures informed changes to original-request preservation, owned review context, quote-only routing and focused retrieval planning. Baseline outputs remain unchanged under ignored `.evaluation-local/source-baseline`; public aggregates are in `evaluation/results/`. The full release evaluation runs **inside the exact candidate image**, using an isolated100-product catalog and its own Qdrant volume, not the host source checkout or existing customer data.

## Release policy

`evaluation/release-policy.json` requires100 completed unique cases, expected per-agent coverage, no unscored execution errors, candidate image identity and145 scored answers/290 valid judge calls. Per-agent floors are0.87/0.89/0.89/0.87 and maximum absolute regression from baseline is0.03. Answer floors are correctness/completeness0.80,relevance0.85,faithfulness0.90.

Critical checkout/idempotence/ownership/stock checks must be present and pass for every journey; forbidden early mutations or confirmation-token leakage block release independently of averages. These are operational thresholds declared before the full candidate run, not statistical significance limits. Missing data cannot silently count as success.

## Run and inspect

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


## Intermediate candidate finding

The first full CPU-image candidate passed 97/100: retrieval 30/30, cart 25/25, coordinator 25/25, journeys 17/20. Its journey score 0.85 was below the declared 0.87 floor, so it was rejected. The three failures were multi-product SQL lookups without name/ID selectors. A new server-side resolver uses literal catalog names (not evaluation labels) to fill missing SQL selectors; targeted reruns of those three journeys passed. The subsequent complete image evaluation passed 100/100 and the unchanged gate, as recorded below. Earlier candidate results remain in `evaluation/results/candidate-iteration1.json`; targeted checks do not replace the benchmark.

Long-term preference-memory proposals are not enabled in these live journeys; conversation history is exercised, while owner/version/deletion memory guards have separate offline tests. Do not claim complete live long-term-memory quality from this set.


## Resource and failure audit

New runs capture worker CPU/RAM and, on native CUDA, sampled whole-device VRAM/utilization. Per-case observations describe the shared worker while that case runs; parallel cases overlap and cannot be charged individual resource ownership. Summary peaks include model startup and exclude the browser, Qdrant and cloud servers. These are sampled observations, not continuous peak guarantees.

Release gating also checks raw judge IDs, schema-valid score coverage and aggregate arithmetic rather than trusting summary counters alone. Failed-but-completed runs are exported to LangSmith even when the gate blocks publication. SQL projections may omit eligibility fields; constraints are checked against frozen SQL facts while any contradictory returned facts still fail.

Cart/coordinator counts include paraphrase variants of 12 and 10 underlying operation templates; they are not 25 independent behavior types or independent statistical trials. The 20 journeys use different product pairs. This coverage remains narrower than real shopper traffic.

## Verified released candidate — 23 October 2026

Both the released Docker CPU image and native GPU workflow run passed **100/100**: retrieval 30/30, cart 25/25, coordinator 25/25 and journeys 20/20. The released image passed every required critical check and the unchanged quality policy. Its application fingerprint matches the native GPU run.

| Released CPU answer metric | Normalized mean | Coverage |
|---|---:|---:|
| Correctness | 90.34% | 145/145 replies |
| Completeness | 93.10% | 145/145 replies |
| Relevance | 95.00% | 145/145 replies |
| Faithfulness | 95.69% | 145/145 replies |

All **290/290** rubric judgments were valid. These are normalized judge means, not percentages of conversations passed. Baseline means were correctness 88.79%, completeness 91.72%, relevance 95.17% and faithfulness 94.83%; relevance did not improve. No statistical significance or held-out generalization is claimed. The earlier 97/100 CPU candidate and interrupted vector-service failure remain retained separately; neither substitutes for final release evidence.

The released CPU experiment is `market-image-39986061885-1` in LangSmith; 100 root case IDs were independently checked against the frozen dataset after export. [Public release record](RELEASE_VERIFICATION.md), [CPU summary](../evaluation/results/docker-cpu-final.json), [answer scores](../evaluation/results/docker-answer-judgments.json), [GPU summary](../evaluation/results/native-gpu-final.json).
