import pytest
from app.agents.retrieval.agent import create_agent as retrieval
from app.agents.cart.agent import create_agent as cart
from app.config import Settings
from app.utils.prompt_loader import load_prompt


def test_agent_owns_prompt_and_tools(products):
    database,_,items=products
    agent=retrieval(database, None)
    assert agent.name == 'retrieval'
    result=agent.tools['product_details'](items[0]['product_id'])
    assert result['price'] == 85
    assert 'review' not in result
    assert 'Respond in English' in agent.system_prompt


def test_cart_quote_uses_current_price_and_aggregated_stock(products):
    database,service,items=products
    product_id=items[0]['product_id']
    service.update(product_id,{'price':90})
    quote=cart(Settings(_env_file=None,database_path=database), 1).tools['quote_cart']([{'product_id':product_id,'quantity':2}])
    assert quote['total'] == 180
    assert quote['currency'] == 'USD'
    assert quote['requires_confirmation']
    with pytest.raises(ValueError):
        cart(Settings(_env_file=None,database_path=database), 1).tools['quote_cart']([{'product_id':product_id,'quantity':6},{'product_id':product_id,'quantity':6}])


def test_prompt_path_traversal_rejected():
    with pytest.raises(ValueError):
        load_prompt('../../..','README.md')
