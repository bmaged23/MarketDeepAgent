from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import ValidationError
from app.product_search.schemas import SearchRequest, SearchFilters

router = APIRouter(prefix="/api", tags=["product search"])


def execute_search(request, payload):
    try:
        return request.app.state.search.search(payload.query, payload.filters, payload.limit, payload.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/search")
def search(request: Request, query: str = Query(min_length=1, max_length=1000),
           category_id: int | None = Query(default=None, gt=0),
           min_price: float | None = Query(default=None, ge=0),
           max_price: float | None = Query(default=None, ge=0), in_stock: bool = False,
           limit: int | None = Query(default=None, ge=1, le=100), mode: str = "hybrid"):
    try:
        payload = SearchRequest(query=query, filters=SearchFilters(category_id=category_id,
            min_price=min_price, max_price=max_price, in_stock=in_stock), limit=limit, mode=mode)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid search query, mode, or filter range") from exc
    return execute_search(request, payload)


@router.post("/search")
def search_post(payload: SearchRequest, request: Request):
    return execute_search(request, payload)
