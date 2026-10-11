import pytest
from pydantic import ValidationError
from app.products.catalog_query import CatalogQuery, query_catalog
from app.agents.retrieval.tools import RetrievalTools


def test_filtered_projected_sql_preserves_identity_and_calorie_context(products):
    db, service, items = products
    service.update(items[0]['product_id'], {'calories_per_100':0, 'calorie_basis':'per_100ml', 'calorie_notes':'Brewed'})
    result = query_catalog(db, {'fields':['calories_per_100'], 'all_matches':True}, {'category_id':1, 'in_stock':True})
    assert result['selection']['total_matches'] == 1
    p = result['results'][0]['product']
    assert p['product_id'] == items[0]['product_id'] and p['category_id'] == 1
    assert p['calories_per_100'] == 0 and p['calorie_notes'] == 'Brewed'
    assert p['calorie_basis'] == 'per_100ml' and p['calorie_status'] == 'estimated'
    assert 'price' not in p and 'search_revision' not in p
    assert result['results'][0]['sources'] == ['sql']
    assert RetrievalTools(db,None).product_details(p['product_id'])['calories_per_100'] == 0


def test_sql_pagination_is_stable_and_complete(products):
    db, _, items = products
    first = query_catalog(db, {'limit':1, 'all_matches':True}, {'category_id':1})
    assert first['selection']['total_matches'] == 2 and first['selection']['next_offset'] == 1
    second = query_catalog(db, {'limit':1, 'offset':1}, {'category_id':1})
    assert second['results'][0]['product']['product_id'] != first['results'][0]['product']['product_id']
    assert second['selection']['next_offset'] is None
    assert len(query_catalog(db, {'fields':[]})['results']) == len(items)


@pytest.mark.parametrize('value', [{'fields':['email']}, {'fields':['name; DELETE FROM product']},
    {'sql':'SELECT * FROM person'}, {'limit':101}, {'offset':-1}, {'product_ids':[True]},
    {'min_calories':10,'max_calories':5}])
def test_only_allowed_product_queries_are_accepted(value):
    with pytest.raises(ValidationError): CatalogQuery.model_validate(value)


def test_values_are_literal_bound_parameters(products):
    db, _, _ = products
    assert not query_catalog(db, {'name_contains':"' OR 1=1 --"})['results']
    assert not query_catalog(db, {'name_contains':'%'})['results']
    assert len(query_catalog(db, {'name_contains':'TEA', 'max_calories':0})['results']) == 0
    assert len(query_catalog(db, {'name_contains':'TEA'})['results']) == 1
