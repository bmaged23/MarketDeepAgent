from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field, ConfigDict
from app.authentication.dependencies import current_person
from app.cart.schemas import CartChange, CheckoutConfirmation

router = APIRouter(prefix="/api/cart", tags=["cart"])


class CartUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, strict=True)
    items: list[CartChange] = Field(min_length=1, max_length=100)


@router.get("")
def view(request: Request, person_id: int = Depends(current_person)):
    return request.app.state.cart.view(person_id)


@router.patch("")
def update(payload: CartUpdate, request: Request, person_id: int = Depends(current_person)):
    return request.app.state.cart.update(person_id, [i.model_dump() for i in payload.items], expected_revision=payload.revision)


@router.delete("")
def clear(request: Request, person_id: int = Depends(current_person)):
    return request.app.state.cart.clear(person_id)


@router.post("/quote")
def quote(request: Request, person_id: int = Depends(current_person)):
    return request.app.state.cart.prepare_checkout(person_id)


@router.post("/checkout")
def checkout(payload: CheckoutConfirmation, request: Request, person_id: int = Depends(current_person)):
    return request.app.state.cart.checkout(person_id, payload)
