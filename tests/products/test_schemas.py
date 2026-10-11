import pytest
from app.products.schemas import ProductCreate, ProductUpdate


def test_product_price_stock_and_name_validation():
    base={'name':'Tea','price':'10.25','category_id':1}
    assert ProductCreate(**base).name == 'Tea'
    for patch in [{'name':'   '},{'price':-1},{'price':'1.234'},{'stock_quantity':-1},{'stock_quantity':True},{'category_id':0}]:
        with pytest.raises(ValueError):
            ProductCreate(**{**base,**patch})


def test_updates_allow_nullable_description_not_nullable_price():
    assert ProductUpdate(description=None).model_dump(exclude_unset=True) == {'description':None}
    with pytest.raises(ValueError):
        ProductUpdate(price=None)
