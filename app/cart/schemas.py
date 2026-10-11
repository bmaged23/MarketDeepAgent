from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class CartChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(ge=0, strict=True)


class CheckoutConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    token: str = Field(min_length=1, max_length=200)
    confirmed: bool = Field(strict=True)
    payment_method: Literal["cash_on_delivery"]
    delivery_address: str = Field(min_length=5, max_length=1000)
