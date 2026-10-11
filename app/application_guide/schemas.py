from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

PageID = Literal["shop", "product", "cart", "orders", "profile", "settings"]


class PageContext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    page: PageID = "shop"
    product_id: int | None = Field(default=None, gt=0, strict=True)
    category_id: int | None = Field(default=None, gt=0, strict=True)
    visible_product_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=100)
    referenced_product_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=10)
    search: str = Field(default="", max_length=200)


class UIAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["navigate", "open_product", "apply_search", "refresh_cart"]
    trigger: Literal["automatic", "on_click"] = "automatic"
    page: PageID | None = None
    product_id: int | None = Field(default=None, gt=0, strict=True)
    category_id: int | None = Field(default=None, gt=0, strict=True)
    query: str = Field(default="", max_length=200)

    @field_validator("query", mode="before")
    @classmethod
    def empty_query(cls, value):
        return "" if value is None else value

    @model_validator(mode="before")
    @classmethod
    def product_page_alias(cls, value):
        # These represent the same allowed operation; never accept arbitrary destinations.
        if isinstance(value, dict) and value.get("page") == "product" and value.get("product_id") is not None:
            if value.get("action") in {"navigate", "open_product"}:
                value = {**value, "action": "open_product", "page": None}
        return value

    @model_validator(mode="after")
    def arguments(self):
        if self.action == "navigate" and (not self.page or self.page == "product"):
            raise ValueError("navigate requires an existing non-product page")
        if (self.action == "open_product") != (self.product_id is not None):
            raise ValueError("Only open_product requires a product ID")
        if self.action != "navigate" and self.page is not None:
            raise ValueError("Page is only allowed for navigate")
        if self.action != "apply_search" and (self.category_id is not None or self.query):
            raise ValueError("Search arguments are only allowed for apply_search")
        return self
