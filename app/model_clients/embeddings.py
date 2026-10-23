from threading import Lock


class BGEEmbeddings:
    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name, dimension=1024, device="cpu", batch_size=32, cache_dir=None, revision=None):
        self.model_name, self.dimension, self.device = model_name, dimension, device
        self.batch_size, self.cache_dir = batch_size, cache_dir
        self.revision = revision
        self._model = None
        self._lock = Lock()

    def _get_model(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer(self.model_name, device=self.device, revision=self.revision,
                    cache_folder=str(self.cache_dir) if self.cache_dir else None)
                if model.get_sentence_embedding_dimension() != self.dimension:
                    raise ValueError("Configured embedding dimension does not match model")
                self._model = model
            return self._model

    def encode_documents(self, documents):
        model = self._get_model()
        with self._lock:
            return model.encode(documents, normalize_embeddings=True, show_progress_bar=False, batch_size=self.batch_size).tolist()

    def encode_query(self, query):
        return self.encode_documents([self.QUERY_INSTRUCTION + query])[0]
