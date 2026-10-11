from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from app.cart.schemas import CartChange


class CartDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["view_cart", "update_cart", "clear_cart", "validate_cart", "prepare_checkout", "order_history", "order_status", "review_product", "clarify"]
    items: list[CartChange] = Field(default_factory=list, max_length=100)
    order_id: int | None = Field(default=None, gt=0, strict=True)
    product_id: int | None = Field(default=None, gt=0, strict=True)
    rating: int | None = Field(default=None, ge=1, le=5, strict=True)
    comment: str = Field(default="", max_length=2000)
    clarification: str = Field(default="", max_length=1000)

    @field_validator("items", mode="before")
    @classmethod
    def unused_items(cls, value):
        return [] if value is None else value

    @model_validator(mode="after")
    def action_arguments(self):
        if (self.action == "update_cart") != bool(self.items):
            raise ValueError("Only update_cart requires items")
        if (self.action in {"order_status", "review_product"}) != (self.order_id is not None):
            raise ValueError("Order status and product reviews require an order ID")
        if (self.action == "review_product") != (self.product_id is not None):
            raise ValueError("Only review_product requires product_id")
        if self.action == "review_product" and self.rating is None and not self.comment:
            raise ValueError("A review requires a rating or comment")
        if self.action != "review_product" and (self.rating is not None or self.comment):
            raise ValueError("Feedback belongs only to review_product")
        if self.action == "clarify" and not self.clarification:
            raise ValueError("Clarification question required")
        return self
