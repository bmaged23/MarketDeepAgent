# USD demo catalog pricing

The 100 seed products use illustrative US-style grocery retail prices, assigned individually
for the package described. These are demo estimates, not current retailer quotations, exchange-rate
conversions or supplier-backed selling prices. Existing product names, package sizes and IDs are unchanged.

[BLS average retail food prices](https://www.bls.gov/regions/mid-atlantic/data/averageretailfoodandenergyprices_usandWest_table.htm)
were checked as a sanity reference for common staples (flour, pasta, bread, milk and produce). Published
units differ from catalog units; branded/imported products and package premiums are estimated.

| Product/package | USD demo price |
| --- | ---: |
| All-Purpose Flour 1kg | $1.49 |
| Whole Milk 1L | $1.49 |
| Apple Juice 1L | $2.29 |
| White Sandwich Bread 600g | $2.49 |
| Lipton tea, 100 bags | $5.49 |
| Croissant, single | $1.49 |
| Croissants, pack of four | $4.99 |
| Basmati rice, 5kg | $16.99 |
| Extra virgin olive oil, 1L | $11.99 |

Canonical fresh-install prices are in data/seed_products.py PRODUCTS. The existing SQLite catalog
was updated transactionally on 2026-10-11. data/catalog_price_changes.json records every previous
and new price. Saved historical orders and item unit prices are unchanged. Existing carts use current
prices; outstanding checkout quotes with changed prices require fresh preparation/confirmation.

Price triggers update BM25 state and queue Qdrant payload/revision synchronization. Process pending
jobs from your terminal with the virtual environment active:

```bash
python -m app.product_indexing.commands process --limit 100
```

Text/vector contents are unchanged. The processor reuses matching existing embeddings when possible.
Search filters and returned prices already use current SQL prices; this command synchronizes Qdrant
metadata. No live Qdrant synchronization was completed in the restricted agent environment.

The retrieval evaluation budget cases now use rice under $20 and sparkling water under $1.50.
All 48 gold-labeled products were checked against updated price filters. Existing saved test reports
still reflect the former prices; rerun evaluations to refresh them.
