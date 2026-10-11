import pytest
from qdrant_client import QdrantClient,models
from app.product_search.vector_index import QdrantProductIndex
from app.product_indexing.processor import IndexingProcessor


@pytest.fixture
def vectors():
    client=QdrantClient(':memory:')
    index=QdrantProductIndex('', 'test_products', 2, 'test-model', client=client)
    yield index
    index.close()


def test_qdrant_real_client_upsert_search_delete(products,vectors):
    _,_,items=products
    vectors.upsert(items[0],[1,0],'hash1')
    vectors.upsert(items[1],[0,1],'hash2')
    hits=vectors.search([1,0],[items[0]['product_id'],items[1]['product_id']],10)
    assert hits[0][0] == items[0]['product_id']
    assert vectors.search([1,0],[items[1]['product_id']],10)[0][0] == items[1]['product_id']
    vectors.upsert(items[0],[1,0],'hash1')
    assert len(vectors.revisions()) == 2
    vectors.delete(items[0]['product_id'])
    assert len(vectors.revisions()) == 1


def test_qdrant_dimension_mismatch_is_explicit(products,vectors):
    _,_,items=products
    with pytest.raises(ValueError):
        vectors.upsert(items[0],[1,0,0],'hash')
    vectors.client.create_collection('test_products',vectors_config=models.VectorParams(size=3,distance=models.Distance.COSINE))
    with pytest.raises(ValueError):
        vectors.ensure_collection()


def test_processor_with_real_local_qdrant(products,vectors):
    database,service,items=products
    class Encoder:
        def encode_documents(self,documents):
            return [[1,0] for _ in documents]
    processor=IndexingProcessor(database,Encoder(),vectors)
    assert processor.run_once()['done'] == 3
    service.delete(items[0]['product_id'])
    assert processor.run_once()['done'] == 1
    assert len(vectors.revisions()) == 2


def test_metadata_updates_reuse_embedding(products,vectors):
    database,service,items=products
    class Encoder:
        calls=0
        def encode_documents(self,documents):
            self.calls += 1
            return [[1,0] for _ in documents]
    encoder=Encoder()
    processor=IndexingProcessor(database,encoder,vectors)
    assert processor.process(items[0]['product_id']) == 'done'
    service.update(items[0]['product_id'],{'price':99,'stock_quantity':8})
    assert processor.process(items[0]['product_id']) == 'done'
    assert encoder.calls == 1
    service.update(items[0]['product_id'],{'description':'A new description'})
    assert processor.process(items[0]['product_id']) == 'done'
    assert encoder.calls == 2


def test_calorie_update_reembeds_and_updates_vector_payload(products,vectors):
    database,service,items=products
    class Encoder:
        calls=0
        def encode_documents(self,documents):
            self.calls+=1
            return [[1,0] for _ in documents]
    encoder=Encoder();processor=IndexingProcessor(database,encoder,vectors)
    product_id=items[0]['product_id']
    assert processor.process(product_id)=='done'
    service.update(product_id,{'calories_per_100':0,'calorie_basis':'per_100ml','calorie_status':'estimated','calorie_notes':'Brewed without sugar'})
    assert processor.process(product_id)=='done'
    assert encoder.calls==2
    payload=vectors.client.retrieve(vectors.collection,ids=[product_id],with_payload=True)[0].payload
    assert payload['calories_per_100']==0 and payload['calorie_basis']=='per_100ml'


def test_vector_and_sql_queries_share_product_and_category_ids(products,vectors):
    from app.products.catalog_query import query_catalog
    database,service,items=products
    product=items[0]
    vectors.upsert(product,[1,0],'identity')
    point=vectors.client.retrieve(vectors.collection,ids=[product['product_id']],with_payload=True)[0]
    row=query_catalog(database,{'product_ids':[product['product_id']]})['results'][0]['product']
    assert point.id == point.payload['product_id'] == row['product_id']
    assert point.payload['category_id'] == row['category_id']
    service.update(product['product_id'],{'category_id':2})
    from app.database.connection import connection
    from app.products.queries import get_product
    with connection(database) as conn: changed=get_product(conn,product['product_id'])
    vectors.upsert(changed,[1,0],'changed-category')
    assert vectors.revisions()[product['product_id']]['category_id'] == 2
    assert not query_catalog(database,{'product_ids':[product['product_id']]},{'category_id':1})['results']
