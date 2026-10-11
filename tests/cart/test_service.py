import pytest
from app.cart.service import CartService
from app.database.connection import connection
from app.utils.errors import ServiceError


@pytest.fixture
def carts(products):
    database, products_service, items = products
    with connection(database, write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('Test','One','one@example.test')")
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('Test','Two','two@example.test')")
    return CartService(database), products_service, items


def confirmation(token, **changes):
    return {"token": token, "confirmed": True, "payment_method": "cash_on_delivery",
            "delivery_address": "Test delivery address", **changes}


def test_cart_validation_persistence_and_removal(carts):
    service, _, items = carts
    assert not service.view(1)["valid"]
    p = items[0]["product_id"]
    service.update(1, [{"product_id": p, "quantity": 2}])
    assert service.view(1)["total"] == 170
    assert not service.view(2)["items"]
    service.update(1, [{"product_id": p, "quantity": 0}])
    assert not service.view(1)["items"]


def test_batch_update_rolls_back_entire_cart_on_invalid_stock(carts):
    service, _, items = carts
    with pytest.raises(ServiceError):
        service.update(1, [{"product_id": items[0]["product_id"], "quantity": 2},
                           {"product_id": items[1]["product_id"], "quantity": 1}])
    assert service.view(1)["items"] == []


def test_checkout_atomic_idempotent_and_owned(carts):
    service, products_service, items = carts
    p = items[0]["product_id"]
    service.update(1, [{"product_id": p, "quantity": 2}])
    quote = service.prepare_checkout(1)
    assert quote["ready"] and service.history(1) == []
    assert stock(service.database_path, p) == 10
    with pytest.raises(ServiceError):
        service.checkout(2, confirmation(quote["confirmation_token"]))
    result = service.checkout(1, confirmation(quote["confirmation_token"]))
    order = result["order"]
    assert order["total_amount"] == 170
    assert order["payment_status"] == "unpaid"
    assert not order["tracking_available"]
    assert not service.view(1)["items"]
    assert stock(service.database_path, p) == 8
    repeat = service.checkout(1, confirmation(quote["confirmation_token"]))
    assert repeat["already_completed"]
    assert len(service.history(1)) == 1
    assert stock(service.database_path, p) == 8
    with pytest.raises(ServiceError):
        service.order(2, order["order_id"])


@pytest.mark.parametrize("change", ["price", "stock", "cart", "expiry", "clear"])
def test_checkout_rejects_stale_or_invalid_quotes(carts, change):
    service, products_service, items = carts
    p = items[0]["product_id"]
    service.update(1, [{"product_id": p, "quantity": 2}])
    token = service.prepare_checkout(1)["confirmation_token"]
    if change == "price": products_service.update(p, {"price": 100})
    elif change == "stock": products_service.update(p, {"stock_quantity": 1})
    elif change == "cart": service.update(1, [{"product_id": p, "quantity": 3}])
    elif change == "clear": service.clear(1)
    else:
        with connection(service.database_path, write=True) as conn:
            conn.execute("UPDATE checkout_quotes SET expires_at=0 WHERE token=?", (token,))
    with pytest.raises(ServiceError):
        service.checkout(1, confirmation(token))
    assert service.history(1) == []


def test_confirmation_and_gateway_are_not_faked(carts):
    service, _, items = carts
    service.update(1, [{"product_id": items[0]["product_id"], "quantity": 1}])
    token = service.prepare_checkout(1)["confirmation_token"]
    with pytest.raises(ServiceError):
        service.checkout(1, confirmation(token, confirmed=False))
    with pytest.raises(ValueError):
        service.checkout(1, confirmation(token, payment_method="credit_card"))
    assert service.history(1) == []


def test_strict_quantities_and_unknown_customer(carts):
    service, _, items = carts
    with pytest.raises(ValueError):
        service.update(1, [{"product_id": items[0]["product_id"], "quantity": True}])
    with pytest.raises(ServiceError):
        service.view(999)


def stock(database, product_id):
    with connection(database) as conn:
        return conn.execute("SELECT stock_quantity FROM product WHERE product_id=?", (product_id,)).fetchone()[0]


def test_stock_cannot_be_oversold_between_customers(carts):
    service, _, items = carts
    p = items[0]["product_id"]
    service.update(1, [{"product_id": p, "quantity": 6}])
    service.update(2, [{"product_id": p, "quantity": 6}])
    first = service.prepare_checkout(1)["confirmation_token"]
    second = service.prepare_checkout(2)["confirmation_token"]
    service.checkout(1, confirmation(first))
    with pytest.raises(ServiceError):
        service.checkout(2, confirmation(second))
    assert stock(service.database_path, p) == 4
    assert service.history(2) == []
    assert service.view(2)["items"][0]["quantity"] == 6


def test_review_only_after_delivered_owned_purchase(carts):
    from app.product_reviews.service import ProductReviewService
    service, _, items = carts
    p = items[0]["product_id"]
    service.update(1, [{"product_id": p, "quantity": 1}])
    token = service.prepare_checkout(1)["confirmation_token"]
    order_id = service.checkout(1, confirmation(token))["order"]["order_id"]
    reviews = ProductReviewService(service.database_path)
    payload = {"order_id": order_id, "product_id": p, "rating": 5, "comment": "Great tea"}
    with pytest.raises(ServiceError): reviews.submit(1, payload)
    with connection(service.database_path, write=True) as conn:
        conn.execute("UPDATE orders SET status_id=(SELECT status_id FROM order_status WHERE label='delivered') WHERE order_id=?", (order_id,))
    with pytest.raises(ServiceError): reviews.submit(2, payload)
    with pytest.raises(ServiceError): reviews.submit(1, {**payload, "product_id": items[2]["product_id"]})
    result = reviews.submit(1, payload)
    assert result["rating"] == 5 and result["comment"] == "Great tea"
    result = reviews.submit(1, {**payload, "rating": 4})
    assert reviews.summary(p) == {"review_count": 1, "rating_count": 1, "average_rating": 4.0}
    order = service.order(1, order_id)
    assert order["review_eligible"]
    assert order["shipping_status"] == "delivered"
    assert order["reviews"][0]["rating"] == 4


@pytest.mark.parametrize("payload", [{"rating": 0}, {"rating": 6}, {"rating": True}, {"comment": "  "}])
def test_invalid_review_feedback(payload):
    from app.product_reviews.schemas import ProductReview
    with pytest.raises(ValueError):
        ProductReview.model_validate({"order_id": 1, "product_id": 1, **payload})


def test_checkout_rolls_back_order_and_stock_if_completion_fails(carts, monkeypatch):
    service, _, items = carts
    p = items[0]["product_id"]
    service.update(1, [{"product_id": p, "quantity": 2}])
    token = service.prepare_checkout(1)["confirmation_token"]
    def fail(*args):
        raise RuntimeError("simulated failure after stock deduction")
    monkeypatch.setattr(service, "_order", fail)
    with pytest.raises(RuntimeError):
        service.checkout(1, confirmation(token))
    assert stock(service.database_path, p) == 10
    assert service.view(1)["items"][0]["quantity"] == 2
    with connection(service.database_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
        assert conn.execute("SELECT order_id FROM checkout_quotes WHERE token=?", (token,)).fetchone()[0] is None


@pytest.mark.parametrize("payload", [{"rating": 4}, {"comment": "Good product"}])
def test_feedback_can_be_rating_or_comment_only(payload):
    from app.product_reviews.schemas import ProductReview
    assert ProductReview.model_validate({"order_id": 1, "product_id": 1, **payload})
