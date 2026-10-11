from threading import RLock


class QdrantProductIndex:
    def __init__(self, url, collection, dimension, model_name, api_key="", client=None, timeout=10):
        self.url, self.collection = url, collection
        self.dimension, self.model_name = dimension, model_name
        self.api_key, self._client, self.timeout = api_key, client, timeout
        self._lock = RLock()

    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    from qdrant_client import QdrantClient
                    self._client = QdrantClient(url=self.url, api_key=self.api_key or None, timeout=self.timeout)
        return self._client

    def ensure_collection(self):
        from qdrant_client import models
        with self._lock:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(self.collection, vectors_config=models.VectorParams(
                    size=self.dimension, distance=models.Distance.COSINE))
            info = self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            if not isinstance(vectors, models.VectorParams) or vectors.size != self.dimension or vectors.distance != models.Distance.COSINE:
                raise ValueError("Qdrant collection vector configuration does not match this project")

    def upsert(self, product, vector, content_hash):
        from qdrant_client import models
        if len(vector) != self.dimension:
            raise ValueError("Embedding dimension mismatch")
        self.ensure_collection()
        self.client.upsert(self.collection, points=[models.PointStruct(
            id=product["product_id"], vector=vector,
            payload={"product_id": product["product_id"], "revision": product["search_revision"],
                     "document_hash": content_hash, "embedding_model": self.model_name,
                     "name": product["name"], "category_id": product["category_id"],
                     "price": float(product["price"]), "stock_quantity": product["stock_quantity"],
                     "image_path": product.get("image_path"),
                     **{field: product.get(field) for field in ("calories_per_100","calorie_basis","calorie_status","calorie_source","calorie_notes")}},
        )], wait=True)

    def get_embedding(self, product_id, content_hash):
        """Reuse unchanged product text embeddings for price/stock/image updates."""
        self.ensure_collection()
        points = self.client.retrieve(self.collection, ids=[product_id], with_payload=True, with_vectors=True)
        if not points:
            return None
        point = points[0]
        payload = point.payload or {}
        if payload.get("document_hash") == content_hash and payload.get("embedding_model") == self.model_name:
            return point.vector
        return None

    def delete(self, product_id):
        from qdrant_client import models
        if self.client.collection_exists(self.collection):
            self.client.delete(self.collection, points_selector=models.PointIdsList(points=[product_id]), wait=True)

    def search(self, vector, eligible_ids, limit):
        from qdrant_client import models
        if not eligible_ids:
            return []
        if len(vector) != self.dimension:
            raise ValueError("Embedding dimension mismatch")
        if not self.client.collection_exists(self.collection):
            raise RuntimeError("Product vector collection has not been indexed")
        result = self.client.query_points(
            collection_name=self.collection, query=vector,
            query_filter=models.Filter(must=[models.HasIdCondition(has_id=eligible_ids),
                models.FieldCondition(key="embedding_model", match=models.MatchValue(value=self.model_name))]),
            limit=limit, with_payload=False,
        )
        return [(int(point.id), point.score) for point in result.points]

    def revisions(self):
        if not self.client.collection_exists(self.collection):
            return {}
        result, offset = {}, None
        while True:
            points, offset = self.client.scroll(self.collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
            for point in points:
                result[int(point.id)] = point.payload or {}
            if offset is None:
                return result

    def close(self):
        if self._client is not None:
            self._client.close()
