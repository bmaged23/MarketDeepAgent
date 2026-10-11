from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Name = Annotated[str, Field(min_length=1, max_length=250)]
Price = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class NutritionFields(BaseModel):
    calories_per_100: float | None = Field(default=None, ge=0, le=2000, allow_inf_nan=False, description="Energy in kcal per 100 g or 100 ml, specified by calorie_basis.")
    calorie_basis: Literal['per_100g','per_100ml'] = 'per_100g'
    calorie_status: Literal['estimated','label_verified'] = 'estimated'
    calorie_source: str | None = Field(default=None, max_length=1000)
    calorie_notes: str | None = Field(default=None, max_length=1000)


class ProductCreate(NutritionFields):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Name
    description: str | None = Field(default=None, max_length=8000)
    price: Price
    stock_quantity: int = Field(default=0, ge=0, strict=True)
    category_id: int = Field(gt=0, strict=True)
    image_path: str | None = Field(default=None, max_length=500)


class ProductUpdate(NutritionFields):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Name | None = None
    description: str | None = Field(default=None, max_length=8000)
    price: Price | None = None
    stock_quantity: int | None = Field(default=None, ge=0, strict=True)
    category_id: int | None = Field(default=None, gt=0, strict=True)
    image_path: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def reject_required_nulls(self):
        for field in {"name", "price", "stock_quantity", "category_id"} & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
