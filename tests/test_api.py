import pytest
pytest.importorskip("fastapi")
pytest.importorskip("pydantic_settings")
import asyncio
import httpx
from app.config import Settings
from app.main import create_app


class Embeddings:
    def encode_query(self, query):
        return [1,0]


class Vectors:
    def search(self, *args):
        raise ConnectionError('offline')
    def close(self):
        pass


def test_api_product_admin_and_hybrid_fallback(catalog, inline_asgi_handlers):
    database,_=catalog
    settings=Settings(_env_file=None,database_path=database,admin_api_key='test-key',embedding_dim=2)
    async def scenario():
        transport = httpx.ASGITransport(app=create_app(settings,Embeddings(),Vectors()))
        async with httpx.AsyncClient(transport=transport,base_url='http://market.test') as client:
            product={'name':'Tea','price':10,'category_id':1,'stock_quantity':5,'calories_per_100':0,'calorie_basis':'per_100ml','calorie_status':'estimated','calorie_notes':'Brewed unsweetened'}
            assert (await client.post('/api/products',json=product)).status_code == 401
            response=await client.post('/api/products',json=product,headers={'X-Admin-Key':'test-key'})
            assert response.status_code == 201
            product_id=response.json()['product']['product_id']
            detail=(await client.get(f'/api/products/{product_id}')).json()
            assert detail['calories_per_100']==0 and detail['calorie_basis']=='per_100ml'
            assert detail['calorie_status']=='estimated'
            result=await client.get('/api/search',params={'query':'tea'})
            assert result.status_code == 200
            assert result.json()['degraded']
            assert (await client.get('/api/search',params={'query':' ','mode':'bm25'})).status_code == 422
            assert (await client.get('/api/products',params={'category_id':-1})).status_code == 422
            status=await client.get(f'/api/products/{product_id}/index-status',headers={'X-Admin-Key':'test-key'})
            assert status.json()['status'] == 'pending'
    asyncio.run(scenario())


def test_config_rejects_invalid_weights():
    with pytest.raises(ValueError):
        Settings(_env_file=None,bm25_weight=0.8,vector_weight=0.8)
