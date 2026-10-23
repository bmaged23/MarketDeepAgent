# MarketDeepAgent evaluation

The current candidate dataset is `datasets/market-agents-v1.jsonl`: 100 frozen synthetic scenarios (30 retrieval, 25 cart, 25 coordinator, 20 six-turn shopping journeys). `catalog-v1.json` contains only the public seeded catalog. Its manifest hashes both artifacts and pins the embedding revision. Freeze these before running live models; never generate reference answers from model outputs.

Each scenario stores constraints separately from evidence. Stable product IDs identify expected retrieval evidence; frozen SQL facts support answer checks. Runtime `chunk_0` labels are not ground truth. Cart/coordinator cases have initial state, expected decisions and forbidden effects. Journeys retain the same isolated customer/conversation across turns, check exact cart quantities and totals, then test explicit confirmation, duplicate submission and ownership.

## Distinct measurements

- Direct hybrid retrieval: nDCG@5, recall@5, precision@5 and reciprocal rank against product IDs.
- Retrieval agent: approved evidence, SQL facts, filter satisfaction, search budget, pagination and completeness. Valid SQL/hybrid alternatives are accepted.
- Cart agent: action/state correctness, quantities, stock preservation, quote-only checkout, reviews and ownership.
- Coordinator: delegation and tool order, grounded evidence, reply format and checkout-token separation.
- Journeys: each user turn, resulting SQL state, actual tool calls, confirmation/idempotence and owner checks.
- Answer judging and resource reports are separate from deterministic workflow scores. A completed request is not automatically a quality pass.

`python -m scripts.evaluation.run_suite` runs actual cloud agents, local BGE and Qdrant. Raw inputs/outputs and intermediate tool traces are stored only under ignored `.evaluation-local/`. The public `results/` directory is for aggregate reports after inspection. Existing `app.agents.*.evaluation` scripts remain useful specialist runners; `--offline` means scripted models and cannot establish live quality.

This is an exposed regression set with mechanically constructed expectations, not independent human-reviewed shoppers, an untouched generalization benchmark or a claim of perfect accuracy. Starter positive retrieval labels are not exhaustive. Full source-based pilot and container-based release runs must be identified separately.
