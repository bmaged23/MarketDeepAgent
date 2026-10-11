from fastapi import APIRouter, Request, Depends
from app.authentication.dependencies import current_person
from app.utils.errors import ServiceError

router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/orders")
def create_order(request: Request, person_id: int = Depends(current_person)):
    raise ServiceError(409, "Prepare and confirm checkout through /api/cart/quote and /api/cart/checkout")


@router.get("/orders")
def my_orders(request: Request, person_id: int = Depends(current_person)):
    return request.app.state.cart.history(person_id)


@router.get("/orders/{owner_id}")
def get_orders(owner_id: int, request: Request, person_id: int = Depends(current_person)):
    if owner_id != person_id: raise ServiceError(403, "You can only view your own orders")
    return request.app.state.cart.history(person_id)
