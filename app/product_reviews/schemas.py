from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    order_id: int = Field(gt=0, strict=True)
    product_id: int = Field(gt=0, strict=True)
    rating: int | None = Field(default=None, ge=1, le=5, strict=True)
    comment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def feedback_required(self):
        if self.rating is None and not self.comment:
            raise ValueError("Supply a rating or a comment")
        return self
