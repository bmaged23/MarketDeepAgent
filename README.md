# MarketDeepAgent

An English grocery marketplace with SQLite product storage, persistent BM25 indexing, BGE embeddings, and Qdrant hybrid retrieval. Product images remain in `products/images/`; prices are in USD.

The indexing/search foundation and the retrieval agent workflow are implemented. Retrieval uses Ollama to rewrite/split requests and check completeness, and the same Ollama model to approve a batch of retrieved chunks. The customer coordinator now delegates to retrieval and cart through a local CLI; a storefront chat interface remains future work.

## Setup

The project has its own `.venv` and root requirements files:

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

For a new checkout, create the environment with `python3 -m venv .venv` and copy `.env.example` to `.env`. Set `OLLAMA_API_KEY` and a private `ADMIN_API_KEY`. Never commit `.env`.

Use the existing Qdrant container at `http://localhost:6333`. This project uses the separate `market_products` collection. The optional Compose service runs a separate instance on port 6335; if used, change `QDRANT_URL` accordingly.

```bash
python -m app.product_indexing.commands migrate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8600 --reload
```

Open `http://127.0.0.1:8600`; API documentation is at `/docs`. The old `UI.backend.main:app` entry point remains compatible.

In a second terminal, activate `.venv` and start the persistent indexing worker:

```bash
python -m app.product_indexing.commands watch
```

The embedding model loads lazily. Its first use downloads `BAAI/bge-large-en-v1.5` unless already cached. `EMBEDDING_CACHE_DIR` controls its cache; `EMBEDDING_DEVICE=cpu` is the default and can be changed to `cuda` on a compatible machine. Query embeddings use BGE's retrieval instruction; document embeddings do not. Both are normalized and dimensions are checked.

## Product indexing

SQLite is authoritative. Database triggers maintain FTS5 documents and indexing jobs in the same transaction as product changes, including stock changes from orders and category renames. All supported writers therefore share the same synchronization behavior.

A worker reads the latest product, generates an embedding, and upserts its Qdrant point using the SQL product ID. It checks the product revision before writing. A short SQLite write transaction serializes the external write with product changes. Encoding happens outside that transaction. This favors correctness for the current small catalog; a slow Qdrant request can briefly block SQL writers.

Failed jobs retain their operation and revision, record a safe error class, and retry with exponential backoff. A crash after a successful vector write is safe to retry. Metadata-only changes reuse existing embeddings when the document hash and model match. Deletion creates a durable cleanup job. Products with order history cannot be deleted.

The current catalog migration preserves the existing products and builds BM25 immediately. Vector indexing is asynchronous: the API returns a product and its indexing state, rather than claiming both stores have committed together.

```bash
# Queue all current products (also use after changing embedding models)
python -m app.product_indexing.commands index-all

# Process one batch; optionally retry failed jobs immediately
python -m app.product_indexing.commands process --limit 100 --force

# Inspect job counts
python -m app.product_indexing.commands status

# Repair missing/stale vectors and remove orphan points
python -m app.product_indexing.commands reconcile
python -m app.product_indexing.commands process --force

# Rebuild keyword documents from SQL
python -m app.product_indexing.commands rebuild-bm25
```

Changing embedding dimensions requires a new Qdrant collection. Changing model or document formatting requires reindexing. Reconciliation checks revisions, document hashes, and model names. Direct edits to `search_revision` or search tables are unsupported. Use migrations and product services for schema and product changes.

## Search

The storefront's search box calls `/api/search`. Category browsing continues to use `/api/products`.

```bash
curl 'http://127.0.0.1:8600/api/search?query=tea&max_price=100&in_stock=true'
```

`GET /api/search` supports `query`, `category_id`, `min_price`, `max_price`, `in_stock`, `limit`, and `mode` (`hybrid`, `bm25`, or `vector`). `POST /api/search` accepts the same search as structured JSON, with filter fields grouped under `filters`.

BM25 searches product names, categories, and descriptions, weighting names most strongly. Semantic retrieval searches BGE vectors. Both paths use SQL eligibility to apply identical filters. Results refresh product details from SQL after retrieval; Qdrant payload prices are not authoritative.

The default hybrid formula is:

```text
score = 0.3 * normalized_BM25 + 0.7 * normalized_cosine_similarity
```

Each candidate list is min-max normalized to `[0, 1]`. FTS5 scores are reversed first because lower scores rank better. Missing candidates contribute zero. Equal-score lists, including a singleton, give each returned candidate 1. Ties break by product ID. These are query-relative ranking scores, not probabilities; candidate counts affect normalization and should be tuned with evaluation data.

Set `SEARCH_FUSION_METHOD=rrf` to compare Reciprocal Rank Fusion. BM25-only/vector-only modes use their own rankings. Hybrid search falls back to BM25 when embedding or vector retrieval fails and returns `degraded=true`; explicit vector-only requests return HTTP 503 instead.

For this catalog, vector eligibility uses SQL product IDs in a Qdrant filter. This is deliberately simple for 100 products; a larger catalog would need a more scalable filtering strategy.

## Configuration

Settings live in `app/config.py`, load root `.env` automatically, and validate types and ranges. Relative database/cache paths resolve from the project root. Secrets are masked in settings representations and never returned through the API.

| Setting | Default / purpose |
| --- | --- |
| `LLM_PROVIDER` | `ollama` |
| `OLLAMA_MODEL` | `gpt-oss:120b` |
| `OLLAMA_BASE_URL` | `https://ollama.com` |
| `OLLAMA_API_KEY` | Private cloud credential |
| `OLLAMA_TIMEOUT_SECONDS` | `120` |
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` |
| `EMBEDDING_DIM` | `1024` |
| `EMBEDDING_DEVICE` | `cpu` |
| `EMBEDDING_BATCH_SIZE` | `32` |
| `EMBEDDING_CACHE_DIR` | `data/model_cache` |
| `DATABASE_PATH` | `data/products.db` |
| `QDRANT_URL` | `http://localhost:6333` |
| `QDRANT_COLLECTION` | `market_products` |
| `QDRANT_API_KEY` | Optional private server credential |
| `QDRANT_TIMEOUT_SECONDS` | `10` |
| `SEARCH_FUSION_METHOD` | `weighted_sum`, or `rrf` |
| `BM25_WEIGHT` | `0.3` |
| `VECTOR_WEIGHT` | `0.7`; both weights must sum to 1 |
| `BM25_CANDIDATES` | `50` |
| `VECTOR_CANDIDATES` | `50` |
| `SEARCH_DEFAULT_LIMIT` | `10` |
| `SEARCH_MAX_LIMIT` | `100` |
| `RRF_K` | `60` |
| `INDEXING_POLL_SECONDS` | `2` |
| `INDEXING_BATCH_SIZE` | `100` |
| `INDEXING_MAX_RETRY_SECONDS` | `300` |
| `ADMIN_API_KEY` | Required by product write and indexing-status endpoints |

## Product administration

`POST /api/products`, `PATCH /api/products/{id}`, `DELETE /api/products/{id}`, and `GET /api/products/{id}/index-status` require `X-Admin-Key`, matching `.env`'s `ADMIN_API_KEY`. Missing configuration disables administration. The local `.env` contains a generated administrator key; `.env.example` contains no secrets.

Example create request body:

```json
{
  "name": "Mint Tea",
  "description": "Mint tea bags, box of 20",
  "price": 75.00,
  "stock_quantity": 30,
  "category_id": 1,
  "image_path": "products/images/chamomile_tea.png"
}
```

The image path is optional and must reference an existing file under `products/images/`. This phase does not add an image-upload endpoint. Successful writes return their SQL product and asynchronous indexing job.

## Code organization

- `app/products/`, `customers/`, `orders/`: routes, validation schemas, business services, SQL queries.
- `app/product_indexing/`: indexing documents, durable jobs, processing, rebuild/reconciliation commands.
- `app/product_search/`: BM25 and vector adapters, score fusion, search API, evaluation.
- `app/database/`: SQLite transactions and versioned migrations.
- `app/model_clients/`: embedding and Ollama clients plus shared construction.
- `app/agents/<agent>/`: each agent's `agent.py`, `tools.py`, and `prompts/system.md`.
- `app/utils/`: shared text, prompt loading, logging, business errors, and password helpers.
- `tests/`: tests grouped by the features they exercise.

There are three roles: `agents/retrieval/` retrieves evidence, `agents/cart/` manages carts and orders, and `agents/customer/` coordinates conversation and delegates to both specialists. Each owns agent.py, tools.py and prompts/. The customer coordinator runs through a local CLI; storefront chat and authenticated chat HTTP endpoints are not implemented.

## Validation

```bash
python -m pytest -q
python -m app.product_search.evaluation --modes bm25 vector hybrid --limit 5
```

Tests exercise actual SQLite/FTS5 transactions and the actual Qdrant client in local mode, using deterministic embeddings. They cover score normalization, 50/50 fusion, filter consistency, fallback, stale jobs, retries, deletion, reconciliation, metadata embedding reuse, product validation, order stock synchronization, and agent tools. API tests require the full requirements installation.

The labeled evaluation file is a small initial set, not a comprehensive quality benchmark. Evaluation reports recall@k, precision@k, reciprocal rank, and degraded-query counts. Index the vectors before comparing semantic and hybrid quality. BM25 can be evaluated independently with `--modes bm25`.

The inherited customer flow still identifies users by `person_id` and does not issue authenticated sessions. Authentication/authorization for customer orders must be completed before public deployment. Seed ratings/reviews are synthetic and are excluded from embedding documents and advisor evidence. Payments and conversational chat are outside this implementation phase.

Reference behavior: [SQLite FTS5 and BM25](https://www.sqlite.org/fts5.html), [BGE model instructions](https://huggingface.co/BAAI/bge-large-en-v1.5), [Qdrant Python client](https://github.com/qdrant/qdrant-client).

## Retrieval agent

Flow: rewrite/split → existing hybrid search → Ollama approved chunk IDs → keep binary approval=1 chunks → Ollama completeness check → targeted follow-up searches or done. Approved evidence accumulates across rounds. Each role keeps its own tools.py and prompts folder; no search SQL or fusion code is duplicated.

Retrieval now uses Ollama for rewriting, batched relevance approval, and completeness validation. The judge receives all new chunks from a round and returns approved chunk IDs; only approved SQL evidence accumulates before follow-up searches or completion. Venice/Jev is no longer called or required; its retained adapter/configuration is inactive. Runtime output remains ephemeral.

```bash
python -m app.agents.retrieval.commands "Find black tea under 100 USD and whole wheat bread"
```

RetrievalAgent returns its result in memory; the API returns JSON and the CLI prints JSON without saving a file. Only evaluation/test reports are persisted. The result contains `retrieval_ok`, `status`, `sections` grouped by query/filter with approved SQL product chunks, combined `context` with a query heading above each group, missing information, round/search trace and reported model token usage. It does not generate a customer answer or place orders. A product appearing under multiple queries retains each query’s provenance. Synthetic reviews/ratings are excluded. Prices/stock describe the retrieval-time SQL snapshot.

`POST /api/retrieval` accepts `{"query":"Find black tea and bread"}` and returns the same result. Restart the API after configuration changes. Missing credentials or failed/malformed model decisions return 503, not successful validation. Ollama Cloud does not currently support schema-enforced structured outputs, so planning/completeness JSON is validated locally with bounded repair attempts. [Ollama documentation](https://docs.ollama.com/capabilities/structured-outputs)

Limits in `app/config.py` / `.env`: `RETRIEVAL_MAX_ROUNDS=3`, `RETRIEVAL_MAX_SEARCHES=8`, `RETRIEVAL_QUERIES_PER_ROUND=3`, `RETRIEVAL_RESULTS_PER_QUERY=5`, `RETRIEVAL_JSON_RETRIES=1`, `JEV_TIMEOUT_SECONDS=30`, `OLLAMA_TEMPERATURE=0`. Unresolved requests return partial/insufficient evidence with retrieval_ok=false when a budget is exhausted, queries repeat, or catalog facts cannot be found. Relevance approval alone is not proof that the original request is fully covered.

## Retrieval-agent evaluation (2026-10-11)

Run from the project root with the virtual environment active:

```bash
python -m app.agents.retrieval.evaluation --max-cases 3
python -m app.agents.retrieval.evaluation --max-cases 48
```

Default report: `data/evaluation_reports/retrieval_agent.json`; reruns replace it. `--output` overrides the destination, `--split tune|test|all` selects cases, and `--tools-only` skips Ollama while still testing hybrid search. Default is three of the existing 48 cases to keep initial live model use small.

The harness directly checks categories, product_details, compare_products and search_products, plus missing-product, duplicate-comparison and invalid-price errors. Direct search is checked using the first selected case; each selected agent case runs the full workflow. Calls include explicit arguments, outputs, durations and exception types. Model traces contain JSON content only, without reasoning, client credentials or headers. Relevance judge inputs and binary decisions are recorded separately. Agent checks cover expected names, SQL factual fidelity, filter propagation, approved-only context, query headings, completion, search budget and degradation. Failures are preserved and remaining cases continue. Failed checks give process exit code 1. Positive labels are incomplete: extra approved products still require human relevance review. This is a test report, not persisted production retrieval output.

Verification: 71 non-API tests passed, including four new harness tests with temporary SQLite and fake clients. CLI help checked. No live Ollama/Venice/Qdrant execution was verified in the network-restricted agent session. Comparison now requires at least two distinct IDs. Selected cases can exceed executed cases if setup fails; inspect setup_error_type and agent_cases in the report.

## Cart, checkout, customer conversation and feedback

```bash
source .venv/bin/activate
# Replace CUSTOMER_ID with your existing customer ID:
python -m app.agents.customer.commands --person-id CUSTOMER_ID --interactive
python -m app.agents.cart.commands --person-id CUSTOMER_ID "Show my cart"
python -m app.agents.cart.commands --person-id CUSTOMER_ID "Show my previous orders"
```

In interactive customer chat, ask to find/add products, change quantities, view the cart or checkout.
After the checkout quote, `/confirm` asks for delivery address, supported payment method
(`cash_on_delivery`) and an explicit `yes`. `/quit` exits. Quotes expire after 900 seconds by default;
price/cart changes or insufficient stock require a new quote. Actual order creation reduces stock
and clears the cart atomically. Repeating the same token returns the same order without a second
stock deduction. COD orders are unpaid and awaiting fulfillment, not automatically paid or shipped.
Online payment is not connected; no payment-provider choice was supplied. Shipping is recorded order
status only: there is no carrier integration, tracking number or delivery estimate.

For noninteractive explicit checkout:

```bash
python -m app.agents.cart.commands --person-id CUSTOMER_ID --confirm-token QUOTE_TOKEN --confirmed --payment-method cash_on_delivery --delivery-address "Your delivery address"
```

Each customer ID is supplied by trusted local application/CLI context, never selected by the model.
These commands do not add web authentication. No new unauthenticated cart/chat HTTP endpoints were
introduced; the legacy person-ID order endpoints remain as before. The browser localStorage cart
is not yet synchronized with the new persistent agent cart. Retrieval outputs and chat history remain
in memory/stdout; cart, checkout quotes, orders and customer feedback are SQL business records.

Once an owned order is recorded as delivered, a customer may give 1–5 stars, an optional comment,
or a comment alone for a product in that order. Example: "Rate product 1 in order 12 four stars and
comment 'Good tea'". Missing/ambiguous review details require clarification. A second review for the
same purchased order/product updates that customer's review. Models cannot mark orders delivered.
Feedback is stored separately from synthetic seed ratings/reviews; it does not relabel seed data as
verified feedback. Order details include the customer's feedback and review eligibility.

Settings: CART_QUOTE_TTL_SECONDS=900, CART_MAX_ITEMS=100, CART_JSON_RETRIES=1,
CUSTOMER_JSON_RETRIES=1, CUSTOMER_HISTORY_MESSAGES=20. All are bounded in config.py and listed
in .env.example. User-private .env was extended without exposing existing credentials.

Verification: 102 non-API tests passed. Tests cover atomic batch updates, invalid stock, stale/expired
quotes, rollback after order creation, overselling across two customers, idempotent checkout,
customer order/quote ownership, unpaid COD status, optional and invalid reviews, delivered-purchase
requirements, cart/coordinator delegation and confirmation-token exclusion from answer-model inputs.
Both new CLI help pages and source compilation checked. Applied migrations to the project database;
existing product/person/orders/order_items counts were preserved. No customer order was placed in
the project database during this task. Live Ollama customer/cart flow and browser/API integration have
not been verified in this restricted session.

## Separate cart/customer evaluation scripts (2026-10-11)

Run live model tests from the project root:

```bash
python -m app.agents.cart.evaluation
python -m app.agents.customer.evaluation
```

Reports default to data/evaluation_reports/cart_agent.json and customer_agent.json, respectively.
Reruns replace these test reports. --output changes the destination. --max-cases 3 selects a small
initial run; --case CASE_ID selects one named scenario. --offline uses scripted model decisions
(and fixture retrieval candidates for customer testing) rather than live model quality evaluation.

Cart has 12 isolated agent scenarios: empty cart, batch additions, quantity change, removal, clear,
stock validation, checkout preparation, owned history/status, delivered feedback, blocked early
feedback, and ambiguous product clarification. A separate direct workflow checks all ten CartTools
methods, including trusted completion, stock deduction and repeated-token idempotence.
Customer has 10 scenarios: greeting, product lookup, retrieval-before-addition, cart view, checkout
preparation, explicit confirmed checkout, history/status, accepted delivered feedback and blocked
early feedback. Confirmed checkout is supplied by the test harness as explicit trusted confirmation,
never an LLM-selected authorization. Both modes use actual SQL service transactions.

Each case copies only catalog categories/product fields into a fresh temporary SQLite database and
creates synthetic customers. No real customers, orders, addresses, carts or reviews are copied.
Temporary fixtures are deleted afterwards. Live customer tests query existing Qdrant read-only;
SQL stock/order mutations are confined to the temporary database and no indexing jobs are processed.
No real order, payment or shipment is created. Requires two catalog products with stock >=3.
Synthetic delivered orders are test fixtures, not real delivery updates.

Reports include scenario query, expected actions/delegation, actual results, checks, model usage,
component-tagged tool/model inputs and outputs, timings and safe failures/HTTP diagnostics. Model
reasoning, credentials and headers are excluded. Failed tests exit 1 and print failed steps/checks
rather than only a boolean. Customer prose factuality needs human review; checks automatically
validate routing and SQL state, not semantic truth of every generated sentence. Offline reports
are explicitly marked offline_scripted and cannot establish live Ollama correctness.

Verification: 12/12 cart and 10/10 customer cases plus the direct all-cart-tools workflow passed in
offline mode. The full non-API suite reported 106 passing tests before the final shared-scenario
refactor; focused harness/trace regression tests also passed afterwards. Both CLI help pages verified.
Regression tests assert source database contents are unchanged and private customers are excluded.
Live cart/customer model runs remain unverified in this network-restricted session. Existing
retrieval_vanila.json and retrieval_agent.json reports were preserved.

Catalog prices are package-aware USD demo estimates; see [catalog pricing](data/catalog_pricing.md). Fresh seeds and existing SQL prices agree. After repricing, run `python -m app.product_indexing.commands process --limit 100` to synchronize pending Qdrant metadata jobs.

## Page-aware customer assistant

Restart the backend after updating, then sign in and click the **AI assistant** tab on the right:

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8600 --reload
```

Open `http://localhost:8600`. The resizable panel remains beside the market on desktop and fills
mobile screens. The customer agent receives the current page, selected product from SQL, and the
available page titles/descriptions; it delegates product discovery to retrieval and cart/order work
to cart. Approved products appear as cards. Typed actions navigate Shop, Cart, Orders, Profile or
Settings, open products, apply searches or refresh the cart. Navigation retains the conversation.
Profile and settings changes use their forms. Checkout requires the quoted confirmation form;
chat alone cannot authorize placing an order. Cash on delivery stays unpaid; no carrier tracking
or online payment gateway is connected.

Registration/login now issue server-owned session cookies. Sign in again after upgrading: old
localStorage identity/cart values are no longer used. Cart, orders, conversations and memory APIs
use the authenticated customer, never a browser-supplied person_id. Mutating requests use CSRF
confirmation. Browser and cart agent share the same SQL cart; concurrent browser edits are checked
against its revision. Legacy POST /api/orders is disabled in favor of POST /api/cart/checkout.

Long-term preferences live in versioned SQLite records and a separate `customer_memories` Qdrant
collection, created lazily on first synchronization. Recall always filters by customer and checks
SQL ownership/version. The model proposes explicit current-message preferences with source quotes;
Settings lets customers disable memory, edit/delete facts, or separately delete chat history.
Deleted/edited facts stop being recalled immediately, including while vector synchronization is
unavailable. Failed sync jobs remain queued. Retry more queued memories with:

```bash
python -m app.customer_memory.commands --limit 100
```

Chat stores user/assistant messages and a bounded summary; raw retrieval chunks and traces remain
in memory. The small application guide is a page registry sent directly to the model. New bounded
settings are listed in .env.example: SESSION_TTL_SECONDS, SESSION_COOKIE_SECURE, MEMORY_COLLECTION,
MEMORY_RECALL_TOP_K, MEMORY_MIN_SCORE, MEMORY_MAX_RECORDS, MEMORY_PROPOSALS_PER_TURN,
MEMORY_SYNC_BATCH_SIZE, CONVERSATION_SUMMARY_CHARS and CHAT_TURN_LOCK_SECONDS. Set secure cookies
when serving over HTTPS; local HTTP defaults remain usable.

Validation: 118 Python tests and three Node DOM-stub assistant tests passed. HTTP tests exercise the
ASGI application with deterministic model/vector clients and inline handlers, without opening a
socket. Local Qdrant tests exercise memory filters/version/deletion. JavaScript syntax and Python
compilation checked. Live Ollama/Docker Qdrant and browser rendering remain unverified here.

```bash
python -m pytest -q
node tests/frontend/assistant.test.cjs
```

Product follow-ups such as "show it to me" include recently shown product IDs, reloaded from SQL.
UI-only requests open known products/pages or apply search directly from the customer plan; unknown
products are resolved through retrieval. Product opening is limited to selected/referenced/approved
items. Cart refresh errors no longer block navigation. Restart the server and hard-refresh browser
after updating; no reindexing is required for these interaction changes. Latest regression validation:
124 Python tests and six Node DOM-stub tests passed; live Ollama/browser behavior remains unverified.

## Intent-aware suggestions and shared cart (2026-10-11)

CustomerPlan adds interaction (answer/view_product/add_to_cart/view_cart/navigate/checkout). UIAction
adds trigger=automatic|on_click (automatic default for compatibility). Product questions return
optional View product/Add to cart choices; explicit show requests open directly; clear add requests
use cart tools directly, stay on current page and offer View cart. Explicit show-cart requests open
cart. CustomerAgent normalizes product suggestions to on_click for answer/add intent and cart
navigation to on_click after successful update/clear unless view_cart was explicitly planned. It
removes refresh_cart from reply actions and adds a bounded optional cart offer after mutations.
Frontend skips automatic execution for on_click, hides refresh-cart controls and synchronizes SQL
cart/badge after replies. Checkout still requires the explicit quote confirmation form. Viewing a
product never authorizes adding it; recommendation choices do not mutate cart until selected.

Integration test uses actual CustomerAgent, CartAgent and SQL CartService through the authenticated
chat API with scripted model decisions: addition updates the same GET /api/cart used by browser,
other customer stays isolated; following show-cart changes navigation without adding again.
127 Python tests and 9 Node DOM-stub tests passed. No new migration/provider/dependency or indexing
changes; live model/browser remain unverified. Restart/hard-refresh to load prompts/client contract.

## Chat formatting, scrolling and contextual choices (2026-10-11)

New UI/frontend/js/markdown.js renders a safe Markdown subset using only DOM text nodes and
allowlisted elements: bold/emphasis, headings, lists, inline/fenced code, quotes and HTTP(S) links.
Raw model HTML is never parsed; unsafe link schemes remain literal text. User messages remain
plain text. index.html loads the helper before assistant.js; style.css adds readable Markdown styles
and constrains chat scrolling (min-height:0, overflow-anchor:none). focusChatAnswer scrolls only the
message pane to the beginning of the latest assistant answer after action/product cards are added.

Assistant navigation buttons are merged with corresponding approved product-card View controls.
Actions targeting the currently visible cart/product/search are not repeated; card View buttons
are hidden for the selected product. Backend action normalization does not offer View cart after
a mutation if cart is already open, or optional View for the selected product. Prompts instruct the
model not to ask whether to open what is already visible. Repeat explicit-view replies acknowledge
the existing view. Existing cart sharing and automatic refresh/explicit checkout semantics remain.

Verification: 128 Python tests and 13 Node DOM-stub tests passed; includes Markdown safety/format,
pane scroll positioning, duplicate View merging and already-open cart/product choices. JS syntax
and git diff --check passed. Live browser layout/scroll behavior still needs user's visual check.
No new dependency, provider, migration, indexing or business data changes. Restart/reload backend
and hard-refresh browser to load client helper/prompts.

## Product calories

All 100 demo products include explicitly **estimated** kcal per 100 g or 100 ml, displayed on
product pages/cards and available to the assistant. Preparation matters: brewed drinks, dry
rice/pasta and raw edible portions use different bases. These are not verified product labels;
see [nutrition provenance and operations](data/catalog_nutrition.md).

The local SQL catalog and BM25 are updated. Synchronize the queued nutrition changes to Qdrant:

```bash
source .venv/bin/activate
python -m app.product_indexing.commands process --limit 100
```

Restart the backend and refresh the browser to load the updated UI and prompts. For another
checkout, `python -m app.products.nutrition` fills missing demo calories without overwriting
existing supplied values.

## Structured product retrieval

The retrieval agent can choose hybrid search, validated SQL product selection, or both. SQL
selection supports category/price/stock filters, product IDs, literal name matching, calorie
bounds and projected fields (or all public product fields). The planner receives input/output
JSON schemas. Product/category IDs are shared with Qdrant, and SQL remains authoritative.
Full-category requests use pagination and matching counts rather than hybrid top-3 results.
No model-authored SQL is executed and no average-specific tool is required. Calorie projections
retain units, estimate status and preparation notes; incomplete selections cannot be reported
as complete coverage. RETRIEVAL_SQL_MAX_RESULTS and RETRIEVAL_RELEVANCE_BATCH_SIZE default to 100.
Restart the backend after updating prompts/code; no reindexing is required for this query feature.

## Repeated shopping tests

Run isolated multi-turn customer/retrieval/cart journeys, including two orders per conversation:

```bash
python -m app.agents.customer.journey_evaluation --repetitions 3
# Scripted offline workflow checks, with no live model-quality claim:
python -m app.agents.customer.journey_evaluation --offline --repetitions 3
```

Reports are saved separately as data/evaluation_reports/shopping_journeys_live.json and
shopping_journeys_offline.json. Only catalog data is cloned into temporary SQL; synthetic
customers/orders and disabled shared memory protect real account state. Live mode requires
Ollama credentials, cached/downloadable BGE and reachable Qdrant. Offline mode uses scripted
model decisions and constant test vectors with actual SQL/FTS/fusion/local-Qdrant plumbing.
A final answer-model failure after a committed cart update now returns the saved SQL receipt
rather than prompting an ambiguous retry. Pending/unpaid cash-on-delivery orders are expected.

Current requests are explicitly separated from historical context in agent prompts. Clear
checkout and order-read requests use customer-scoped quote/history/status tools, so prior cart
additions cannot be replayed during those operations. Checkout confirmation remains an explicit
trusted form action. Cart viewing uses a SQL snapshot without a second answer-model call.
The reviewed pre-fix live journey report is archived; a post-fix live run is still required.

Customer replies ground simple cart changes and pending cash-on-delivery explanations in SQL results. Complete approved all-product calorie requests include every matching product. `CUSTOMER_RECEIPT_MAX_ITEMS` controls cart receipt length (default 10).
