from app.product_indexing.service import reconcile,schedule_all
from app.product_indexing.processor import IndexingProcessor
from app.database.connection import connection
from app.product_search.vector_index import QdrantProductIndex
from qdrant_client import QdrantClient


def test_reconciliation_repairs_missing_stale_and_orphan_points(products):
    database,_,items=products
    vectors=QdrantProductIndex('','test',2,'test-model',client=QdrantClient(':memory:'))
    class Embeddings:
        def encode_documents(self,documents):
            return [[1,0] for _ in documents]
    processor=IndexingProcessor(database,Embeddings(),vectors)
    processor.run_once()
    assert reconcile(database,vectors) == 0
    vectors.delete(items[0]['product_id'])
    orphan={**items[1],'product_id':999}
    vectors.upsert(orphan,[1,0],'orphan')
    assert reconcile(database,vectors) == 2
    assert processor.run_once()['done'] == 2
    assert set(vectors.revisions()) == {item['product_id'] for item in items}
    assert schedule_all(database) == 3
    assert processor.run_once()['done'] == 3
    vectors.close()
