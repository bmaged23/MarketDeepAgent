from pydantic import BaseModel, ConfigDict, Field


class OrderItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(gt=0, strict=True)


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: int = Field(gt=0, strict=True)
    items: list[OrderItemRequest] = Field(min_length=1, max_length=100)
