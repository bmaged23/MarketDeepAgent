# Retrieval evaluation dataset

`search_evaluation.json` contains 48 English, manually authored cases for the current
100-product catalog. It is a starter benchmark, not observed customer traffic or
human-reviewed ground truth. Review the labels before drawing product decisions.

Each case has a stable `case_id`, `query_type`, `split`, natural-language `query`,
structured `filters`, and `relevant_product_names`. Labels use names so they remain
readable and are resolved to SQL IDs at runtime. Keep catalog names unique. Positive
labels describe intended relevant products; other results are treated as irrelevant
by the metrics, so review and expand labels when other valid alternatives appear.

Coverage includes exact names, keywords, description matching, paraphrases, attributes,
shopping intent, fruit-versus-drink disambiguation, explicit price/stock filters,
indirect semantic requests, and misspellings. There are 24 tuning and 24 test cases.
This small split samples the same catalog; it does not establish generalization to
new products. Expand with real shopping queries and user-reviewed relevance labels.

`agent_expectations` prepares cases for a future agent runner: the user message,
expected search action, intended products and filters, SQL as the factual source,
and assertions against invented product facts. These fields are not executed by the
current retrieval evaluator. It does not test tool selection, answers, conversations,
or automatic filter extraction. Filters are passed explicitly to SearchService;
future agent tests should verify extracting them from `user_message`.

## Run from the project root with the virtual environment active

Compare the existing 50/50 configuration to the pure retrievers:

```bash
python -m app.product_search.evaluation --modes bm25 vector hybrid --limit 5 --output data/evaluation_reports/baseline.json
```

Compare weights on tuning cases only:

```bash
python -m app.product_search.evaluation --sweep --split tune --limit 5 --output data/evaluation_reports/weights.json
```

The script tries BM25 percentages 0, 10, ... 100 and complementary vector weights.
`best_weights` contains every tie for highest mean NDCG@5. Reported percentages are
provisional. Vector failures or no vector candidates invalidate weight selection.
Query embeddings are reused across weights. Pure BM25/vector baselines are separate
from the zero-weight endpoints of the hybrid candidate union.

Validate ONE selected weight on held-out test cases. For example, if tuning selected
40% BM25 and 60% vector:

```bash
python -m app.product_search.evaluation --split test --bm25-weight 0.4 --limit 5 --output data/evaluation_reports/heldout.json
```

This override does not modify `.env`. Do not select weights by repeatedly inspecting
held-out performance. Keep 50/50 if tuning is inconclusive; add more independent labels.

Reports include Recall@k (coverage), Precision@k (hits divided by requested k),
reciprocal rank (first relevant hit), binary NDCG@k (ranking of all relevant hits),
degraded-query counts, and per-query expected/returned products, scores and sources.
Sparse positive labels naturally limit Precision@5; use NDCG and recall for tuning.
Scores are normalized ranking scores, not confidence probabilities.

Qdrant and the cached BGE model must be available for semantic evaluation. Normal
hybrid runs exit unsuccessfully when vector search degrades, even though a report
may still be saved. Generated reports are ignored by Git. All commands use the
actual catalog; unit tests use isolated temporary catalogs.

## One-command report with custom percentages

```bash
python -m app.product_search.evaluation --sweep --weights 0.3 0.4 0.5 0.6 0.7 --limit 5
```

This tests BM25 alone, vector alone, and BM25/vector hybrids 30/70, 40/60,
50/50, 60/40, and 70/30 on all dataset cases. Without --weights, --sweep tests
the full 0/100 through 100/0 grid. Every successful evaluation automatically
saves data/evaluation_reports/retrieval_vanila.json under the project root,
replacing the previous report at that path. --output overrides the destination. Console summaries include both pure
baselines, hybrid metrics, ties for best NDCG, and the saved report path; JSON
contains complete per-query results too. All-case comparison is descriptive;
use --split tune for weight selection and --split test for held-out validation.

2026-10-11 price update: catalog now uses plausible USD demo estimates. Price-filter cases retrieval-029 and retrieval-032 use budgets $20 and $1.50 respectively; query/user message/filter expectations were updated together. Gold products remain eligible. Previous report scores are historical until rerun. See catalog_pricing.md.
