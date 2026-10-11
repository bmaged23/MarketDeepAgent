import json
import math
import pytest
from pydantic import ValidationError
from app.config import PROJECT_ROOT
from app.database.connection import connection
from app.products.schemas import ProductCreate,ProductUpdate
from app.products.nutrition import apply_catalog_nutrition
from app.product_indexing.service import product_document,document_hash
from app.product_search.bm25_index import BM25Index
from app.product_search.schemas import SearchFilters
from app.utils.nutrition import nutrition_summary
from app.agents.retrieval.agent import RetrievalAgent


def nutrition(**changes):
    return {'calories_per_100':194,'calorie_basis':'per_100g','calorie_status':'estimated','calorie_source':'Comparable food estimate','calorie_notes':'As sold',**changes}


def test_nutrition_update_queues_vector_and_updates_keyword_index(products):
    database,service,items=products; product_id=items[0]['product_id']
    original=items[0]; before=document_hash(original)
    updated=service.update(product_id,nutrition())['product']
    assert updated['search_revision']==original['search_revision']+1
    assert updated['price']==original['price'] and updated['stock_quantity']==original['stock_quantity']
    assert document_hash(updated)!=before
    assert '194 kcal per 100 g (Estimated)' in product_document(updated)
    with connection(database) as conn:
        assert BM25Index().search(conn,'calories',SearchFilters(),10)[0][0]==product_id
        assert conn.execute('SELECT status FROM product_index_jobs WHERE product_id=?',(product_id,)).fetchone()[0]=='pending'
        conn.execute("UPDATE category SET name='Drinks' WHERE category_id=1")
        assert BM25Index().search(conn,'calories',SearchFilters(),10)[0][0]==product_id


def test_calorie_schema_rejects_invalid_units_and_values():
    for data in [nutrition(calories_per_100=-1),nutrition(calories_per_100=math.nan),nutrition(calories_per_100=math.inf),nutrition(calorie_basis='per_pack'),nutrition(calorie_status='guessed')]:
        with pytest.raises(ValidationError): ProductUpdate.model_validate(data)
    assert ProductCreate(name='Water',price=1,category_id=1,**nutrition(calories_per_100=0,calorie_basis='per_100ml')).calories_per_100==0
    assert '0 kcal per 100 ml' in nutrition_summary(nutrition(calories_per_100=0,calorie_basis='per_100ml'))


def test_backfill_is_idempotent_and_preserves_verified_values(catalog,tmp_path):
    database,service=catalog
    labneh=service.create({'name':'Labneh 500g','price':4.99,'category_id':1})['product']
    bread=service.create({'name':'Toast Bread','price':2.29,'category_id':2,**nutrition(calories_per_100=260,calorie_status='label_verified')})['product']
    assert apply_catalog_nutrition(database)=={'updated':1}
    assert apply_catalog_nutrition(database)=={'updated':0}
    with connection(database) as c:
        row=c.execute('SELECT * FROM product WHERE product_id=?',(labneh['product_id'],)).fetchone()
        assert row['calories_per_100']==194 and row['calorie_status']=='estimated'
        assert c.execute('SELECT calories_per_100 FROM product WHERE product_id=?',(bread['product_id'],)).fetchone()[0]==260


def test_all_100_seed_products_have_explicit_nutrition_records():
    from data.seed_products import PRODUCTS
    records=json.loads((PROJECT_ROOT/'data/catalog_nutrition.json').read_text())['products']
    assert len(records)==100 and {r['name'] for r in records}=={p[0] for p in PRODUCTS}
    assert all(r['calorie_status']=='estimated' and r['calorie_source'] and r['calorie_notes'] for r in records)
    for row in records: ProductUpdate.model_validate({k:v for k,v in row.items() if k not in {'name','reference_url'}})


def test_retrieval_coverage_keeps_calorie_units_and_status():
    product={'product_id':41,'name':'Labneh','description':'Strained yogurt','category':'Dairy','price':4.99,'stock_quantity':10,**nutrition()}
    evidence=RetrievalAgent._evidence([{'query':'labneh calories','filters':{},'chunks':[{'approval':1,'product':product}]}])
    assert evidence[0]['products'][0]['calories_per_100']==194
    assert evidence[0]['products'][0]['calorie_basis']=='per_100g'
    assert evidence[0]['products'][0]['calorie_status']=='estimated'


def test_fresh_seed_populates_all_calories_and_rerun_preserves_catalog(tmp_path,monkeypatch):
    from data import seed_products
    database=tmp_path/'fresh.db';monkeypatch.setattr(seed_products,'DB_PATH',database)
    seed_products.main()
    with connection(database) as c:
        assert c.execute('SELECT COUNT(*) FROM product WHERE calories_per_100 IS NOT NULL').fetchone()[0]==100
        before=[tuple(r) for r in c.execute('SELECT * FROM product ORDER BY product_id')]
    seed_products.main()
    with connection(database) as c: assert before==[tuple(r) for r in c.execute('SELECT * FROM product ORDER BY product_id')]
