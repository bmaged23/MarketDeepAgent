from types import SimpleNamespace
import pytest
from app.database.connection import connection
from app.orders.service import OrderService
from app.utils.errors import ServiceError


def setup_customer(database):
    with connection(database,write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('Test','Customer','test@example.com')")


def payload(product_id, quantities):
    return SimpleNamespace(person_id=1,items=[SimpleNamespace(product_id=product_id,quantity=q) for q in quantities])


def test_duplicate_order_lines_cannot_oversell(products):
    database,_,items=products
    setup_customer(database)
    with pytest.raises(ServiceError):
        OrderService(database).create(payload(items[0]['product_id'],[6,6]))
    with connection(database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 0
        assert conn.execute('SELECT stock_quantity FROM product WHERE product_id=?',(items[0]['product_id'],)).fetchone()[0] == 10


def test_order_commits_total_items_stock_and_index_job_together(products):
    database,_,items=products
    setup_customer(database)
    result=OrderService(database).create(payload(items[0]['product_id'],[1,2]))
    assert result['total_amount'] == 255
    with connection(database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM order_items').fetchone()[0] == 1
        assert conn.execute('SELECT stock_quantity FROM product WHERE product_id=?',(items[0]['product_id'],)).fetchone()[0] == 7
        assert conn.execute('SELECT revision FROM product_index_jobs WHERE product_id=?',(items[0]['product_id'],)).fetchone()[0] == 2
    assert OrderService(database).history(1)[0]['items'][0]['quantity'] == 3
