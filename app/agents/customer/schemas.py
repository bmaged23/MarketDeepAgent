import re
from typing import Literal
from app.application_guide.schemas import UIAction
from app.customer_memory.schemas import MemoryProposal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CustomerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interaction: Literal["answer", "view_product", "add_to_cart", "view_cart", "navigate", "checkout"] = "answer"
    specialist_query: str | None = Field(default=None, min_length=1, max_length=2000)
    actions: list[UIAction] = Field(default_factory=list, max_length=3)
    steps: list[Literal["retrieval", "cart"]] = Field(default_factory=list, max_length=2)


class CustomerReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=10000, description="All marketplace amounts are in US dollars (USD), displayed with the dollar sign ($).")

    actions: list[UIAction] = Field(default_factory=list, max_length=3)
    product_ids: list[int] = Field(default_factory=list, max_length=10, description="Verified product IDs to display as clickable product cards, including choices from live context. Never invent IDs.")
    memories: list[MemoryProposal] = Field(default_factory=list, max_length=3)
    conversation_summary: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def marketplace_currency(self):
        if re.search(r"[€£]\s*-?\d|\b(?:EGP|EUR|GBP)\s*\d|\b\d+(?:[.,]\d+)?\s*(?:EGP|EUR|GBP|euros)\b", self.answer, re.I):
            raise ValueError("Marketplace prices must be expressed in USD")
        return self
