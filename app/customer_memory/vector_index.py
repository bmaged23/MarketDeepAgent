from threading import RLock
from qdrant_client import models


class MemoryVectorIndex:
    def __init__(self, settings, client=None):
        self.settings, self._client = settings, client
        self._lock = RLock()
        self._ready = False

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(url=self.settings.qdrant_url,api_key=self.settings.qdrant_api_key.get_secret_value() or None,timeout=self.settings.qdrant_timeout_seconds)
        return self._client

    def ensure(self):
        with self._lock:
            if self._ready: return
            name = self.settings.memory_collection
            if not self.client.collection_exists(name):
                self.client.create_collection(name,vectors_config=models.VectorParams(size=self.settings.embedding_dim,distance=models.Distance.COSINE))
            params=self.client.get_collection(name).config.params.vectors
            if not isinstance(params,models.VectorParams) or params.size != self.settings.embedding_dim or params.distance != models.Distance.COSINE:
                raise ValueError("Memory collection embedding configuration mismatch")
            self.client.create_payload_index(name,field_name="person_id",field_schema=models.PayloadSchemaType.INTEGER,wait=True)
            self._ready=True

    def upsert(self, memory, vector):
        self.ensure()
        self.client.upsert(self.settings.memory_collection,points=[models.PointStruct(id=memory["memory_id"],vector=vector,
            payload={"person_id":memory["person_id"],"version":memory["version"],"embedding_model":self.settings.embedding_model})],wait=True)

    def delete(self, person_id, memory_id):
        if self.client.collection_exists(self.settings.memory_collection):
            self.client.delete(self.settings.memory_collection,points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.HasIdCondition(has_id=[memory_id]),models.FieldCondition(key="person_id",match=models.MatchValue(value=person_id))])),wait=True)

    def search(self, person_id, vector, limit):
        if not self.client.collection_exists(self.settings.memory_collection): return []
        points=self.client.query_points(collection_name=self.settings.memory_collection,query=vector,
            query_filter=models.Filter(must=[models.FieldCondition(key="person_id",match=models.MatchValue(value=person_id)),
                models.FieldCondition(key="embedding_model",match=models.MatchValue(value=self.settings.embedding_model))]),limit=limit,with_payload=True).points
        return [(int(p.id),(p.payload or {}).get("version"),p.score) for p in points]

    def close(self):
        if self._client is not None: self._client.close()
