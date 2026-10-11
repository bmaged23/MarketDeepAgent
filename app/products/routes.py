from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.database.connection import connection
from app.products.queries import get_product, list_products
from app.products.schemas import ProductCreate, ProductUpdate
from app.products.service import InvalidProduct, ProductNotFound
from app.product_search.schemas import SearchFilters
from app.product_indexing.jobs import status
from app.utils.admin_auth import require_admin

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/categories")
def categories(request: Request):
    with connection(request.app.state.settings.database_path) as conn:
        return [dict(r) for r in conn.execute("SELECT category_id,name FROM category ORDER BY name")]


@router.get("/products")
def products(request: Request, category_id: int | None = Query(default=None, gt=0), search: str | None = None):
    with connection(request.app.state.settings.database_path) as conn:
        return list_products(conn, SearchFilters(category_id=category_id), search)


@router.get("/products/{product_id}")
def product(product_id: int, request: Request):
    with connection(request.app.state.settings.database_path) as conn:
        result = get_product(conn, product_id)
    if result is None:
        raise HTTPException(404, "Product not found")
    return result


def write_result(call):
    try:
        return call()
    except ProductNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except InvalidProduct as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/products", status_code=201, dependencies=[Depends(require_admin)])
def create_product(payload: ProductCreate, request: Request):
    return write_result(lambda: request.app.state.products.create(payload.model_dump(mode="json")))


@router.patch("/products/{product_id}", dependencies=[Depends(require_admin)])
def update_product(product_id: int, payload: ProductUpdate, request: Request):
    return write_result(lambda: request.app.state.products.update(product_id, payload.model_dump(exclude_unset=True, mode="json")))


@router.delete("/products/{product_id}", dependencies=[Depends(require_admin)])
def delete_product(product_id: int, request: Request):
    return write_result(lambda: request.app.state.products.delete(product_id))


@router.get("/products/{product_id}/index-status", dependencies=[Depends(require_admin)])
def index_status(product_id: int, request: Request):
    with connection(request.app.state.settings.database_path) as conn:
        job = status(conn, product_id)
    if job is None:
        raise HTTPException(404, "Indexing job not found")
    return job
