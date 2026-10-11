from typing import Literal
from app.products.catalog_query import CatalogQuery
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.product_search.schemas import SearchFilters


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RetrievalRequest(Decision):
    query: str = Field(min_length=1, max_length=2000)


class SearchTask(Decision):
    query: str = Field(min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    source: Literal["hybrid", "sql", "both"] = "hybrid"
    catalog: CatalogQuery | None = None

    @model_validator(mode="after")
    def query_source(self):
        if self.catalog is not None and self.source not in {"sql", "both"}:
            raise ValueError("Catalog selection requires source=sql or both")
        return self


class RetrievalPlan(Decision):
    rewritten_query: str = Field(min_length=1, max_length=2000)
    queries: list[SearchTask] = Field(min_length=1, max_length=10)


class CoverageDecision(Decision):
    retrieval_ok: bool = Field(strict=True)
    followup_queries: list[SearchTask] = Field(default_factory=list, max_length=10)
    missing_information: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def consistent_completion(self):
        if self.retrieval_ok and (self.followup_queries or self.missing_information):
            raise ValueError("Completed retrieval cannot request more searches or claim missing information")
        return self


class RelevanceDecision(Decision):
    approved_chunk_ids: list[str] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(self.approved_chunk_ids) != len(set(self.approved_chunk_ids)):
            raise ValueError("Approved chunk IDs must be unique")
        return self
