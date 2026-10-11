import pytest
from app.database.connection import connection
from app.product_search.service import SearchService
from app.product_search.schemas import SearchFilters,SearchRequest


class Embeddings:
    def encode_query(self, query):
        return [1,0]


class Vectors:
    def __init__(self):
        self.ids=None
    def search(self, vector, eligible_ids, limit):
        self.ids=eligible_ids
        return [(product_id,1/(index+1)) for index,product_id in enumerate(reversed(eligible_ids))]


def test_hybrid_applies_identical_filters_and_returns_sql_prices(products):
    database,service,items=products
    vectors=Vectors()
    search=SearchService(database,Embeddings(),vectors)
    service.update(items[0]['product_id'],{'price':86})
    result=search.search('tea',SearchFilters(category_id=1,max_price=100,in_stock=True))
    assert vectors.ids == [items[0]['product_id']]
    assert result['results'][0]['product']['price'] == 86
    assert result['results'][0]['sources'] == ['bm25','vector']
    assert result['results'][0]['score'] == 1
    assert result['weights'] == {'bm25':0.5,'vector':0.5}


def test_semantic_failure_falls_back_to_bm25(products):
    database,_,items=products
    class Offline(Vectors):
        def search(self,*args):
            raise ConnectionError()
    search=SearchService(database,Embeddings(),Offline())
    result=search.search('tea',SearchFilters())
    assert result['degraded'] is True
    assert result['results'][0]['product']['product_id'] == items[0]['product_id']
    with pytest.raises(RuntimeError):
        search.search('tea',SearchFilters(),mode='vector')


def test_bm25_mode_does_not_load_embeddings(products):
    database,_,_=products
    search=SearchService(database,None,None)
    assert search.search('tea',SearchFilters(),mode='bm25')['results']
    assert not search.search('!!!',SearchFilters(),mode='bm25')['results']


def test_recheck_sql_after_vector_query(products):
    database,service,items=products
    product_id=items[0]['product_id']
    class Mutation(Vectors):
        def search(self,*args):
            service.update(product_id,{'stock_quantity':0})
            return [(product_id,0.9)]
    result=SearchService(database,Embeddings(),Mutation()).search('tea',SearchFilters(in_stock=True))
    assert all(r['product']['product_id'] != product_id for r in result['results'])


def test_empty_filtered_catalog_skips_embedding_model(products):
    database,_,_=products
    result=SearchService(database,None,None).search('tea',SearchFilters(max_price=1))
    assert result['results'] == []
    assert not result['degraded']


def test_request_validation():
    with pytest.raises(ValueError):
        SearchFilters(min_price=100,max_price=10)
    with pytest.raises(ValueError):
        SearchRequest(query='   ')
    with pytest.raises(ValueError):
        SearchFilters(min_price=float('nan'))


def test_blank_query_and_excessive_limit_rejected(products):
    database,_,_=products
    search=SearchService(database,None,None,max_limit=5)
    with pytest.raises(ValueError):
        search.search('   ',SearchFilters(),limit=1)
    with pytest.raises(ValueError):
        search.search('tea',SearchFilters(),limit=6)
