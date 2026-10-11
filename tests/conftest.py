import pytest
from app.database.connection import migrate, connection
from app.products.service import ProductService


@pytest.fixture
def catalog(tmp_path):
    database = tmp_path / "products.db"
    migrate(database)
    with connection(database, write=True) as conn:
        conn.execute("INSERT INTO category(name) VALUES('Beverages')")
        conn.execute("INSERT INTO category(name) VALUES('Bakery')")
    return database, ProductService(database, tmp_path)


@pytest.fixture
def products(catalog):
    database, service = catalog
    items = [
        {"name":"Black Tea", "description":"Classic black tea bags", "price":85, "stock_quantity":10,"category_id":1},
        {"name":"Coffee", "description":"Ground coffee beans", "price":220, "stock_quantity":0,"category_id":1},
        {"name":"Bread", "description":"Whole wheat bread loaf", "price":30, "stock_quantity":15,"category_id":2},
    ]
    return database,service,[service.create(item)["product"] for item in items]


@pytest.fixture
def inline_asgi_handlers(monkeypatch):
    """ASGI HTTP tests without worker threads, which this sandbox cannot run."""
    import fastapi.routing
    import fastapi.dependencies.utils
    async def inline(callable_fn, *args, **kwargs):
        return callable_fn(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', inline)
    monkeypatch.setattr(fastapi.dependencies.utils, 'run_in_threadpool', inline)
