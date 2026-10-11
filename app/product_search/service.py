import logging
from app.database.connection import connection
from app.products.queries import list_products
from app.product_search.bm25_index import BM25Index
from app.product_search.rank_fusion import reciprocal_rank_fusion, weighted_sum, normalize_scores
from app.utils.text import normalize_text

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, database_path, embeddings, vectors, *, bm25_candidates=50,
                 vector_candidates=50, fusion_method="weighted_sum", bm25_weight=0.5,
                 vector_weight=0.5, rrf_k=60, max_limit=100, default_limit=10):
        self.database_path, self.embeddings, self.vectors = database_path, embeddings, vectors
        self.bm25_candidates, self.vector_candidates = bm25_candidates, vector_candidates
        self.fusion_method, self.bm25_weight, self.vector_weight = fusion_method, bm25_weight, vector_weight
        self.rrf_k, self.max_limit = rrf_k, max_limit
        self.default_limit = default_limit
        self.bm25 = BM25Index()

    def search(self, query, filters, limit=None, mode="hybrid"):
        limit = self.default_limit if limit is None else limit
        if mode not in {"hybrid", "bm25", "vector"}:
            raise ValueError("Unknown search mode")
        query = normalize_text(query)
        if not query:
            raise ValueError("Search query cannot be blank")
        if not 1 <= limit <= self.max_limit:
            raise ValueError("Search limit is outside the configured range")
        # SQL eligibility is authoritative, including changes not yet propagated to Qdrant.
        with connection(self.database_path) as conn:
            eligible = list_products(conn, filters)
            lexical = self.bm25.search(conn, query, filters, max(limit, self.bm25_candidates)) if mode != "vector" else []
        semantic, degraded = [], False
        if eligible and mode != "bm25":
            try:
                semantic = self.vectors.search(self.embeddings.encode_query(query),
                                               [p["product_id"] for p in eligible], max(limit, self.vector_candidates))
            except Exception:
                logger.exception("Vector retrieval unavailable")
                if mode == "vector":
                    raise RuntimeError("Vector search unavailable") from None
                degraded = True
        if mode == "bm25" or degraded:
            ranking = sorted(normalize_scores(lexical, lower_is_better=True).items(), key=lambda item: (-item[1],item[0]))
        elif mode == "vector":
            ranking = sorted(normalize_scores(semantic).items(), key=lambda item: (-item[1],item[0]))
        elif self.fusion_method == "rrf":
            ranking = reciprocal_rank_fusion(lexical, semantic, k=self.rrf_k)
        else:
            ranking = weighted_sum(lexical, semantic, self.bm25_weight, self.vector_weight)
        # Refresh SQL rows after retrieval; deleted products and newly ineligible rows are excluded.
        with connection(self.database_path) as conn:
            current = {p["product_id"]: p for p in list_products(conn, filters)}
        sources = {"bm25": {p for p, _ in lexical}, "vector": {p for p, _ in semantic}}
        results = []
        for product_id, score in ranking:
            if product_id not in current:
                continue
            product = current[product_id]
            for field in ("image_prompt", "search_revision"):
                product.pop(field, None)
            results.append({"product": product, "score": score,
                            "sources": [source for source, ids in sources.items() if product_id in ids]})
            if len(results) == limit:
                break
        return {"query": query, "mode": mode, "fusion_method": self.fusion_method,
                "weights": {"bm25": self.bm25_weight, "vector": self.vector_weight}, "degraded": degraded,
                "degraded_reason": "vector_search_unavailable" if degraded else None,
                "results": results}


def create_search_service(settings, embeddings, vectors):
    return SearchService(settings.database_path, embeddings, vectors,
        bm25_candidates=settings.bm25_candidates, vector_candidates=settings.vector_candidates,
        fusion_method=settings.search_fusion_method, bm25_weight=settings.bm25_weight,
        vector_weight=settings.vector_weight, rrf_k=settings.rrf_k,
        max_limit=settings.search_max_limit, default_limit=settings.search_default_limit)
