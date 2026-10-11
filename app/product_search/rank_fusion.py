def reciprocal_rank_fusion(*rankings, k=60):
    scores = {}
    for ranking in rankings:
        seen = set()
        for rank, (product_id, _) in enumerate(ranking, start=1):
            if product_id in seen:
                continue
            seen.add(product_id)
            scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def normalize_scores(ranking, *, lower_is_better=False):
    """Per-query min-max normalization. Missing products receive zero at fusion.

    An equal-score list receives 1 for each returned candidate; it contains no
    relative score information. SQLite FTS5's smaller scores rank higher.
    """
    if not ranking:
        return {}
    scores = {product_id: (-score if lower_is_better else score) for product_id, score in ranking}
    low, high = min(scores.values()), max(scores.values())
    if high == low:
        return {product_id: 1.0 for product_id in scores}
    return {product_id: (score-low)/(high-low) for product_id,score in scores.items()}


def weighted_sum(bm25_ranking, vector_ranking, bm25_weight=0.5, vector_weight=0.5):
    lexical = normalize_scores(bm25_ranking, lower_is_better=True)
    semantic = normalize_scores(vector_ranking)
    scores = {product_id: bm25_weight*lexical.get(product_id,0.0) + vector_weight*semantic.get(product_id,0.0)
              for product_id in lexical.keys() | semantic.keys()}
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
