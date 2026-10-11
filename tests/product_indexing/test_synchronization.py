import sqlite3
import pytest
from app.database.connection import connection, migrate
from app.product_indexing.processor import IndexingProcessor
from app.products.service import InvalidProduct
from app.product_search.bm25_index import BM25Index
from app.product_search.schemas import SearchFilters


class Embeddings:
    def encode_documents(self, documents):
        return [[1.0,0.0] for _ in documents]


class Vectors:
    def __init__(self):
        self.points = {}
        self.fail = False
    def get_embedding(self, product_id, content_hash):
        return None
    def upsert(self, product, vector, content_hash):
        if self.fail:
            raise ConnectionError("offline")
        self.points[product["product_id"]] = dict(product)
    def delete(self, product_id):
        if self.fail:
            raise ConnectionError("offline")
        self.points.pop(product_id,None)


def test_migrations_are_idempotent(catalog):
    database,_ = catalog
    with connection(database) as conn:
        before = [row[0] for row in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
    migrate(database)
    with connection(database) as conn:
        after = [row[0] for row in conn.execute('SELECT version FROM schema_migrations ORDER BY version')]
    assert before == after and before


def test_create_indexes_keyword_and_queues_vector_atomically(products):
    database,_,items = products
    with connection(database) as conn:
        assert BM25Index().search(conn,'tea',SearchFilters(),10)[0][0] == items[0]['product_id']
        assert conn.execute("SELECT COUNT(*) FROM product_index_jobs WHERE status='pending'").fetchone()[0] == 3


def test_failed_transaction_rolls_back_indexes(products):
    database,_,_ = products
    with pytest.raises(RuntimeError):
        with connection(database,write=True) as conn:
            conn.execute("INSERT INTO product(name,price,category_id) VALUES('Rollback',10,1)")
            raise RuntimeError('abort')
    with connection(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM product WHERE name='Rollback'").fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM product_fts').fetchone()[0] == 3
        assert conn.execute('SELECT COUNT(*) FROM product_index_jobs').fetchone()[0] == 3


def test_retry_and_upsert_are_idempotent(products):
    database,_,items = products
    vectors = Vectors(); vectors.fail=True
    processor=IndexingProcessor(database,Embeddings(),vectors)
    assert processor.run_once()['failed'] == 3
    assert processor.run_once() == {'done':0,'failed':0,'skipped':0}
    vectors.fail=False
    assert processor.run_once(force=True)['done'] == 3
    assert processor.run_once()['done'] == 0
    assert len(vectors.points) == 3


def test_update_and_delete_sync(products):
    database,service,items=products
    vectors=Vectors(); processor=IndexingProcessor(database,Embeddings(),vectors)
    processor.run_once()
    product_id=items[0]['product_id']
    result=service.update(product_id,{'name':'Mint Infusion','description':'Refreshing mint leaves','price':90})
    assert result['product']['search_revision'] == 2
    assert processor.run_once()['done'] == 1
    assert vectors.points[product_id]['price'] == 90
    with connection(database) as conn:
        assert not BM25Index().search(conn,'black',SearchFilters(),10)
        assert BM25Index().search(conn,'mint',SearchFilters(),10)
    service.delete(product_id)
    assert processor.run_once()['done'] == 1
    assert product_id not in vectors.points
    with connection(database) as conn:
        assert not BM25Index().search(conn,'mint',SearchFilters(),10)


def test_change_during_encoding_skips_stale_write(products):
    database,service,items=products
    vectors=Vectors()
    product_id=items[0]['product_id']
    class RacingEmbeddings(Embeddings):
        def encode_documents(self, documents):
            service.update(product_id,{'price':99})
            return super().encode_documents(documents)
    processor=IndexingProcessor(database,RacingEmbeddings(),vectors)
    assert processor.process(product_id) == 'skipped'
    assert not vectors.points
    processor.embeddings=Embeddings()
    assert processor.process(product_id) == 'done'
    assert vectors.points[product_id]['price'] == 99


def test_stock_and_category_changes_schedule_metadata_sync(products):
    database,_,items=products
    with connection(database,write=True) as conn:
        conn.execute("UPDATE product SET stock_quantity=stock_quantity-1 WHERE product_id=?",(items[0]['product_id'],))
        conn.execute("UPDATE category SET name='Drinks' WHERE category_id=1")
    with connection(database) as conn:
        product=conn.execute("SELECT search_revision FROM product WHERE product_id=?",(items[0]['product_id'],)).fetchone()
        assert product[0] == 3
        assert len(BM25Index().search(conn,'drinks',SearchFilters(),10)) == 2


def test_reject_invalid_category_image_and_unknown_field(catalog):
    _,service=catalog
    for changes in [{'category_id':999},{'image_path':'../secret.png'},{'name); DROP TABLE product; --':'bad'}]:
        with pytest.raises(InvalidProduct):
            service.create({'name':'Tea','price':10,'category_id':1,**changes})


def test_same_value_update_does_not_create_new_revision(products):
    _,service,items=products
    result=service.update(items[0]['product_id'],{'price':85})
    assert result['product']['search_revision'] == 1


def test_delete_with_order_history_is_rejected(products):
    database,service,items=products
    with connection(database,write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('Test','Customer','test@example.com')")
        conn.execute("INSERT INTO orders(person_id,status_id) VALUES(1,1)")
        conn.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES(1,?,1,85)",(items[0]['product_id'],))
    with pytest.raises(InvalidProduct):
        service.delete(items[0]['product_id'])
