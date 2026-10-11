# Demo catalog calories

All 100 current products have a calorie estimate in `catalog_nutrition.json` and SQLite. These are
editorial food-type estimates for the demo marketplace, **not verified nutrition labels for these
specific products**. Exact recipes, fat content, sugar content and preparation can differ.

Each record supplies `calories_per_100` (kcal), `calorie_basis` (`per_100g` or `per_100ml`),
`calorie_status` (`estimated` here), `calorie_source` and `calorie_notes`. The dataset also includes an
optional comparison-reference URL. Product names are exact seed matches; IDs are not hard-coded by
the import command. It fills only missing values and skips ambiguous names; existing values,
including supplied label values, are preserved. Source dataset records cover all 100 seed names.

- Tea/coffee and hibiscus/chamomile refer to unsweetened prepared drinks, not dry tea/coffee packages.
- Rice, pasta and dried legumes refer to dry uncooked weight, not cooked portions.
- Fruit/vegetables refer to raw edible portions; whole fruits/heads do not imply a known edible weight.
- Microwave popcorn refers to popped preparation. Plain frozen molokhia excludes added oil.
- Oil estimates use 100 ml; these cannot be converted to grams by assuming equal volume and mass.
- Labneh uses an approximate comparable-food estimate of 194 kcal/100 g. The [Pınar labneh label](https://eng.pinar.com.tr/products/detail-milk/Pinar-Labaneh/2072/2240/0) lists 194.4 kcal/100 g for its own product; the unbranded 500 g catalog item is not assumed to be that brand.

The [FDA nutrition-label guide](https://www.fda.gov/food/new-nutrition-facts-label/how-understand-and-use-nutrition-facts-label) explains product-specific calorie/serving information;
its [raw vegetable reference](https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/nutrition-information-raw-vegetables) uses edible portions. These are reference guidance,
not evidence that every demo estimate came from a measured label or laboratory analysis. Other
food-type estimates are not individually source-verified. No macro/micronutrient values are invented.

Only compute a serving total when the quantity unit/preparation matches the record:
`estimated kcal = calories_per_100 × quantity / 100`. Never present the per-100 value as a whole-pack
value or estimate the weight of an unknown portion. Product pages/cards and agents show estimates.

To fill missing known demo entries on another checkout:

```bash
python -m app.products.nutrition
```

Seeding invokes the same import after migrations. Product create/update APIs accept these fields,
so a trusted administrator can replace estimates with the exact supplied nutrition label, including
source and preparation notes. Keep `calorie_status=estimated` until the exact product label is verified.

SQLite triggers immediately update BM25 and enqueue vector updates for nutrition changes. Product
embedding text/version and Qdrant payload include calorie data; changing it requires re-embedding:

```bash
python -m app.product_indexing.commands process --limit 100
```

The nutrition migration preserves product/customer/order data. An ignored local database backup
was taken before applying it. No live Qdrant updates have been confirmed in this restricted session.
