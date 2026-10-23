from pathlib import Path
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.utils.money import CURRENCY_CODE

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    currency: Literal["USD"] = CURRENCY_CODE
    llm_provider: str = "ollama"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_model: str = "gpt-oss:120b"
    ollama_base_url: str = "https://ollama.com"
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    embedding_revision: str = "d4aa6901d3a41ba39fb536a557fa166f842b0e09"
    embedding_dim: int = Field(default=1024, gt=0)
    embedding_device: str = "cpu"
    database_path: Path = PROJECT_ROOT / "data/products.db"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = "market_products"
    admin_api_key: SecretStr = SecretStr("")
    search_fusion_method: str = "weighted_sum"
    bm25_weight: float = Field(default=0.3, ge=0, le=1, allow_inf_nan=False)
    vector_weight: float = Field(default=0.7, ge=0, le=1, allow_inf_nan=False)
    bm25_candidates: int = Field(default=50, ge=1, le=1000)
    vector_candidates: int = Field(default=50, ge=1, le=1000)
    search_default_limit: int = Field(default=10, ge=1, le=100)
    search_max_limit: int = Field(default=100, ge=1, le=100)
    rrf_k: int = Field(default=60, gt=0)
    qdrant_timeout_seconds: float = Field(default=10, gt=0)
    ollama_timeout_seconds: float = Field(default=120, gt=0)
    ollama_temperature: float = Field(default=0, ge=0, le=2)
    retrieval_max_rounds: int = Field(default=3, ge=1, le=10)
    retrieval_max_searches: int = Field(default=8, ge=1, le=30)
    retrieval_queries_per_round: int = Field(default=3, ge=1, le=10)
    retrieval_relevance_batch_size: int = Field(default=100, ge=1, le=200)
    retrieval_sql_max_results: int = Field(default=100, ge=1, le=100)
    retrieval_results_per_query: int = Field(default=3, ge=1, le=20)
    retrieval_json_retries: int = Field(default=1, ge=0, le=3)
    cart_quote_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    cart_max_items: int = Field(default=100, ge=1, le=100)
    cart_json_retries: int = Field(default=1, ge=0, le=3)
    customer_receipt_max_items: int = Field(default=10, ge=1, le=20)
    customer_history_messages: int = Field(default=20, ge=2, le=100)
    customer_json_retries: int = Field(default=1, ge=0, le=3)
    session_ttl_seconds: int = Field(default=604800, ge=300, le=2592000)
    session_cookie_secure: bool = False
    memory_collection: str = "customer_memories"
    memory_recall_top_k: int = Field(default=5, ge=1, le=20)
    memory_min_score: float = Field(default=0.4, ge=0, le=1, allow_inf_nan=False)
    memory_max_records: int = Field(default=200, ge=1, le=1000)
    memory_proposals_per_turn: int = Field(default=3, ge=1, le=3)
    memory_sync_batch_size: int = Field(default=3, ge=1, le=20)
    conversation_summary_chars: int = Field(default=2000, ge=100, le=2000)
    chat_turn_lock_seconds: int = Field(default=1800, ge=300, le=7200)
    embedding_batch_size: int = Field(default=32, gt=0)
    embedding_cache_dir: Path = PROJECT_ROOT / "data/model_cache"
    indexing_batch_size: int = Field(default=100, gt=0)
    indexing_max_retry_seconds: int = Field(default=300, gt=0)
    indexing_poll_seconds: float = Field(default=2, gt=0)

    @model_validator(mode="after")
    def validate_search(self):
        if self.search_fusion_method not in {"weighted_sum", "rrf"}:
            raise ValueError("SEARCH_FUSION_METHOD must be weighted_sum or rrf")
        if abs(self.bm25_weight + self.vector_weight - 1.0) > 1e-8:
            raise ValueError("BM25_WEIGHT and VECTOR_WEIGHT must sum to 1")
        if self.search_default_limit > self.search_max_limit:
            raise ValueError("SEARCH_DEFAULT_LIMIT must not exceed SEARCH_MAX_LIMIT")
        if self.retrieval_results_per_query > self.search_max_limit:
            raise ValueError("RETRIEVAL_RESULTS_PER_QUERY must not exceed SEARCH_MAX_LIMIT")
        if self.memory_collection == self.qdrant_collection:
            raise ValueError("Memory and product collections must be different")
        return self

    @field_validator("database_path", "embedding_cache_dir", mode="after")
    @classmethod
    def absolute_database_path(cls, value):
        return value if value.is_absolute() else PROJECT_ROOT / value


@lru_cache
def get_settings() -> Settings:
    return Settings()
