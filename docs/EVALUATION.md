# Agent, SQL and answer evaluation

## References precede execution

`evaluation/datasets/market-agents-v1.jsonl` freezes 100 synthetic scenarios, with a seeded catalog snapshot and SHA-256 manifest. Its coverage is 30 retrieval, 25 cart, 25 coordinator and 20 six-turn journeys. Retrieval labels reuse the first30 source-labelled starter queries transparently; extra relevant alternatives may not be exhaustively labelled. Workflow variants and journeys are mechanically authored from catalog facts, not generated from the model's output. The set is exposed regression data, not an untouched generalization benchmark or human-adjudicated real shoppers.

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

Each rubric score is an integer0–4, normalized by dividing by4. Report means and coverage per metric; there is no combined overall answer score. These judgments need human calibration and cannot independently certify truth. Correctness and faithfulness are different: an answer can accurately repeat incomplete evidence while failing to answer the question.

The parser accepts exact JSON code fences but enforces required fields, score ranges and schema. Only invalid responses or transient requests get bounded repair/retry (maximum3 judge attempts). Valid low scores are never retried. Earlier failed tooling attempts are kept privately and are not counted as successful judgments. Monetary cost is not inferred without billing rates.

## Baseline and candidate are separate

The original native-GPU source baseline completed100 cases and passed91: retrieval27/30,cart23/25,coordinator23/25,journeys18/20. Its direct-ranking recall/MRR/nDCG@5 were1.0 on30 known starter queries; precision@5 was0.2467. Answer means over145 replies: correctness0.8879,completeness0.9172,relevance0.9517,faithfulness0.9483. These narrow results do not establish universal accuracy.

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

The first full CPU-image candidate passed97/100: retrieval30/30,cart25/25,coordinator25/25,journeys17/20. Despite the higher total, its journey score0.85 is below the declared0.87 floor, so it is not promoted. The three failures were multi-product SQL lookups without name/ID selectors. A new server-side resolver uses literal catalog names (not evaluation labels) to fill missing SQL selectors; targeted reruns of those three journeys passed. A new full-image run is still required. Earlier candidate results remain in `evaluation/results/candidate-iteration1.json`; targeted checks do not replace the benchmark.

Long-term preference-memory proposals are not enabled in these live journeys; conversation history is exercised, while owner/version/deletion memory guards have separate offline tests. Do not claim complete live long-term-memory quality from this set.
