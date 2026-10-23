from app.model_clients.embeddings import BGEEmbeddings
from app.product_search.vector_index import QdrantProductIndex


def embedding_client(settings):
    return BGEEmbeddings(settings.embedding_model, settings.embedding_dim,
        settings.embedding_device, settings.embedding_batch_size, settings.embedding_cache_dir,
        revision=settings.embedding_revision)


def vector_index(settings):
    return QdrantProductIndex(settings.qdrant_url, settings.qdrant_collection,
        settings.embedding_dim, settings.embedding_model,
        settings.qdrant_api_key.get_secret_value(), timeout=settings.qdrant_timeout_seconds)
