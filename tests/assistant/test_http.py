import asyncio
import httpx
from app.main import create_app
from app.config import Settings
from app.database.connection import connection


class Embeddings:
    def encode_query(self,query): return [1.,0.]
    def encode_documents(self,texts): return [[1.,0.] for _ in texts]


class Vectors:
    def search(self,*args): return []
    def close(self): pass


class MemoryVectors(Vectors):
    def upsert(self,*args): pass
    def delete(self,*args): pass


class Runner:
    def __init__(self,owner,contexts): self.owner,self.contexts=owner,contexts
    def run(self,query,history=None,context=None):
        self.contexts.append((self.owner,context,history))
        return {'answer':'Here are your settings.','results':{},'actions':[{'action':'navigate','page':'settings','product_id':None,'category_id':None,'query':''}],'memory_proposals':[{'key':'drink','text':'Prefers tea','source_quote':'I prefer tea'}],'conversation_summary':'Tea preference'}


def test_authenticated_chat_cart_owner_context_and_checkout(products, inline_asgi_handlers):
    database,_,items=products; contexts=[]
    settings=Settings(_env_file=None,database_path=database,embedding_dim=2)
    app=create_app(settings,Embeddings(),Vectors(),MemoryVectors(),lambda settings,search,owner:Runner(owner,contexts))
    async def scenario():
        transport=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,base_url='http://market.test') as one, httpx.AsyncClient(transport=transport,base_url='http://market.test') as two:
            assert (await one.get('/api/me')).status_code==401
            payload={'first_name':'One','last_name':'Test','email':'one@example.com','password':'testpassword'}
            assert (await one.post('/api/register',json=payload,headers={'Origin':'https://evil.test'})).status_code==403
            assert (await one.post('/api/register',json=payload)).status_code==200
            payload.update(first_name='Two',email='two@example.com')
            assert (await two.post('/api/register',json=payload)).status_code==200
            a={'X-CSRF-Token':one.cookies['market_csrf']}; b={'X-CSRF-Token':two.cookies['market_csrf']}
            assert 'HttpOnly' in (await one.post('/api/login',json={'email':'one@example.com','password':'testpassword'})).headers.get('set-cookie','')
            a={'X-CSRF-Token':one.cookies['market_csrf']}
            body={'query':'I prefer tea','page_context':{'page':'product','product_id':items[0]['product_id'],'visible_product_ids':[99999,items[0]['product_id']]}}
            assert (await one.post('/api/chat',json=body)).status_code==403
            forged={**body,'person_id':2}
            assert (await one.post('/api/chat',json=forged,headers=a)).status_code==422
            response=await one.post('/api/chat',json=body,headers=a)
            assert response.status_code==200, response.text
            result=response.json(); cid=result['conversation_id']
            assert result['actions'][0]['page']=='settings' and result['memory_status']['saved']==1
            assert 'memory_proposals' not in result
            assert contexts[0][0]==1 and contexts[0][1]['selected_product']['name']=='Black Tea'
            assert contexts[0][1]['page_context']['visible_product_ids']==[items[0]['product_id']]
            shop_response=await one.post('/api/chat',json={'query':'I prefer tea','conversation_id':cid,
                'page_context':{'page':'shop','search':'tea','visible_product_ids':[99999,items[0]['product_id']]}},headers=a)
            assert shop_response.status_code==200, shop_response.text
            assert contexts[-1][1]['selected_product'] is None
            assert [p['product_id'] for p in contexts[-1][1]['visible_products']]==[items[0]['product_id']]
            assert contexts[-1][1]['visible_products'][0]['name']=='Black Tea'
            assert (await two.get('/api/conversations/'+cid)).status_code==404
            assert (await two.post('/api/chat',json={**body,'conversation_id':cid},headers=b)).status_code==404
            assert (await two.get('/api/memories')).json()==[]
            update={'revision':0,'items':[{'product_id':items[0]['product_id'],'quantity':2}]}
            assert (await one.patch('/api/cart',json=update,headers=a)).status_code==200
            assert (await two.get('/api/cart')).json()['items']==[]
            assert (await one.patch('/api/cart',json=update,headers=a)).status_code==409
            quote=(await one.post('/api/cart/quote',headers=a)).json()
            confirm={'token':quote['confirmation_token'],'confirmed':True,'delivery_address':'Test street','payment_method':'cash_on_delivery'}
            assert (await two.post('/api/cart/checkout',json=confirm,headers=b)).status_code==404
            assert (await one.post('/api/cart/checkout',json=confirm,headers=a)).status_code==200
            again=(await one.post('/api/cart/checkout',json=confirm,headers=a)).json()
            assert again['already_completed']
            assert len((await one.get('/api/orders')).json())==1
            assert (await two.get('/api/orders')).json()==[]
            assert (await one.post('/api/orders',json={'person_id':1,'items':[]},headers=a)).status_code==409
            assert (await one.post('/api/logout',headers=a)).status_code==200
            assert (await one.get('/api/me')).status_code==401
    asyncio.run(scenario())


def test_product_card_followup_uses_live_reference_and_opens_product(products, inline_asgi_handlers):
    import json
    from app.agents.customer.agent import CustomerAgent
    from app.agents.customer.tools import CustomerTools
    database,product_service,_=products
    apple=product_service.create({'name':'Apples 1kg','description':'Fresh apples','category_id':1,'price':3.99,'stock_quantity':10})['product']
    with connection(database,write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('One','Test','one@example.com')")
    replies=iter([
        {'steps':['retrieval']},
        {'answer':'Here are the apples.'},
        {'steps':[],'actions':[{'action':'navigate','page':'product','product_id':apple['product_id'],'query':None}]},
    ])
    class LLM:
        def chat(self,messages): return {'message':{'content':json.dumps(next(replies))}}
    class Retrieval:
        def run(self,query): return {'sections':[{'query':query,'chunks':[{'approval':1,'product':apple}]}]}
    settings=Settings(_env_file=None,database_path=database,embedding_dim=2)
    factory=lambda settings,search,owner:CustomerAgent(settings,CustomerTools(Retrieval(),None),LLM())
    app=create_app(settings,Embeddings(),Vectors(),MemoryVectors(),factory)
    token,csrf=app.state.sessions.issue(1)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://market.test',cookies={'market_session':token},headers={'X-CSRF-Token':csrf}) as client:
            first=await client.post('/api/chat',json={'query':'can you tell me where to find apples'})
            assert first.status_code==200, first.text
            second=await client.post('/api/chat',json={'query':'can you show it to me','conversation_id':first.json()['conversation_id'],'page_context':{'page':'shop','referenced_product_ids':[apple['product_id']]}})
            assert second.status_code==200,second.text
            assert second.json()['actions'][0]['action']=='open_product'
            assert second.json()['actions'][0]['product_id']==apple['product_id']
            assert second.json()['answer']=='Opening Apples 1kg.'
            assert (await client.get('/api/cart')).json()['items']==[]
    asyncio.run(scenario())


def test_customer_addition_updates_browser_sql_cart_without_opening_it(products, inline_asgi_handlers):
    import json
    from app.agents.customer.agent import CustomerAgent
    from app.agents.customer.tools import CustomerTools
    from app.agents.cart.agent import create_runner as cart_runner
    database,_,items=products
    with connection(database,write=True) as conn:
        for name in ['One','Two']:
            conn.execute("INSERT INTO person(first_name,last_name,email) VALUES(?,'Test',?)",(name,name+'@example.com'))
    replies=iter([
        {'interaction':'add_to_cart','steps':['retrieval','cart']},
        {'answer':'Added two teas to your cart. Would you like to view it?', 'actions':[{'action':'navigate','page':'cart'},{'action':'refresh_cart'}]},
        {'interaction':'view_cart','steps':[],'actions':[{'action':'navigate','page':'cart'}]},
    ])
    class LLM:
        def chat(self,messages): return {'message':{'content':json.dumps(next(replies))}}
    class CartLLM:
        def chat(self,messages): return {'message':{'content':json.dumps({'action':'update_cart','items':[{'product_id':items[0]['product_id'],'quantity':2}]})}}
    class Retrieval:
        def run(self,query): return {'sections':[{'query':query,'chunks':[{'approval':1,'product':items[0]}]}]}
    settings=Settings(_env_file=None,database_path=database,embedding_dim=2)
    factory=lambda settings,search,owner:CustomerAgent(settings,CustomerTools(Retrieval(),cart_runner(settings,owner,CartLLM())),LLM())
    app=create_app(settings,Embeddings(),Vectors(),MemoryVectors(),factory)
    token,csrf=app.state.sessions.issue(1)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://market.test',cookies={'market_session':token},headers={'X-CSRF-Token':csrf}) as client:
            result=await client.post('/api/chat',json={'query':'Add two teas to my cart'})
            assert result.status_code==200,result.text
            assert result.json()['results']['cart']['status']=='ok'
            assert result.json()['actions']==[{'action':'navigate','trigger':'on_click','page':'cart','product_id':None,'category_id':None,'query':''}]
            browser_cart=(await client.get('/api/cart')).json()
            assert browser_cart['items'][0]['quantity']==2
            assert app.state.cart.view(2)['items']==[]
            show=await client.post('/api/chat',json={'query':'Show my cart','conversation_id':result.json()['conversation_id']})
            assert show.status_code==200,show.text
            assert show.json()['actions'][0]['trigger']=='automatic'
            assert show.json()['actions'][0]['page']=='cart'
            assert (await client.get('/api/cart')).json()==browser_cart
    asyncio.run(scenario())


def test_context_only_product_choices_return_verified_sql_cards(products, inline_asgi_handlers):
    database,service,items=products
    with connection(database,write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('One','Test','cards@example.test')")
    class Choices:
        def run(self,query,history=None,context=None):
            return {'answer':'Which would you like to view?', 'results':{}, 'actions':[],
                    'product_ids':[items[0]['product_id'],items[1]['product_id'],items[0]['product_id'],items[2]['product_id'],99999]}
    settings=Settings(_env_file=None,database_path=database,embedding_dim=2)
    app=create_app(settings,Embeddings(),Vectors(),MemoryVectors(),lambda *args:Choices())
    token,csrf=app.state.sessions.issue(1)
    # Cards must reflect current SQL, not an earlier displayed price.
    service.update(items[0]['product_id'],{'price':9.99})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://market.test',cookies={'market_session':token},headers={'X-CSRF-Token':csrf}) as client:
            response=await client.post('/api/chat',json={'query':'Show it to me','page_context':{
                'page':'shop','referenced_product_ids':[items[0]['product_id'],items[1]['product_id']]}})
            assert response.status_code==200,response.text
            cards=response.json()['products']
            assert [p['product_id'] for p in cards]==[items[0]['product_id'],items[1]['product_id']]
            assert cards[0]['price']==9.99
            assert 'search_revision' not in cards[0] and 'image_prompt' not in cards[0]
            assert 'product_ids' not in response.json()
    asyncio.run(scenario())
