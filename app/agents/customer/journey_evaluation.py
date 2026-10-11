"""Repeated shopping journeys, with isolated SQL and explicit live/offline reporting."""
import argparse
import json
import re
from pathlib import Path
import httpx
from qdrant_client import QdrantClient
from app.config import get_settings, PROJECT_ROOT
from app.database.connection import connection
from app.products.queries import list_products
from app.agents.customer.agent import CustomerAgent, create_runner
from app.agents.customer.tools import CustomerTools
from app.agents.cart.agent import create_runner as cart_runner
from app.agents.retrieval.agent import RetrievalAgent
from app.agents.retrieval.tools import RetrievalTools
from app.agents.retrieval.relevance import OllamaRelevanceJudge
from app.assistant.service import AssistantService
from app.assistant.schemas import ChatRequest
from app.cart.service import CartService
from app.conversations.service import ConversationService
from app.customer_memory.service import MemoryService
from app.product_search.service import create_search_service
from app.product_search.vector_index import QdrantProductIndex
from app.model_clients.factory import embedding_client, vector_index
from app.utils.errors import ServiceError
from app.utils.agent_evaluation import evaluation_catalog, ScriptedLLM, record_case, save_report, stock


class OfflineEmbeddings:
    """Constant test embeddings exercise fusion plumbing, never semantic quality."""
    def encode_query(self, query): return [1., 0.]
    def encode_documents(self, texts): return [[1., 0.] for _ in texts]


class NoMemoryVectors:
    def __getattr__(self, name):
        raise AssertionError('Journey memory is disabled; no shared memory writes are permitted')


class RetrievalDecisions:
    """Scripted planning/approval/completeness, with real SQL/hybrid tools."""
    usage = []
    def __init__(self, task, wanted): self.task, self.wanted = task, wanted
    def chat(self, messages):
        payload = json.loads(messages[1]['content'])
        if 'chunks' in payload:
            result = {'approved_chunk_ids':[c['chunk_id'] for c in payload['chunks'] if c['product']['product_id'] in self.wanted]}
        elif 'approved_evidence' in payload:
            result = {'retrieval_ok':True}
        else:
            result = {'rewritten_query':self.task['query'], 'queries':[self.task]}
        return {'message':{'content':json.dumps(result)}}


def evaluate_journey(settings, repetition, offline=False, embeddings=None, vectors=None):
    cases = []
    with evaluation_catalog(settings) as (isolated, rows, eligible):
        # Only catalog data is cloned. Synthetic IDs never write shared user memory.
        memory = MemoryService(isolated, embeddings, NoMemoryVectors())
        memory.set_enabled(1,False); memory.set_enabled(2,False)
        a = next((p for p in rows if p['name']=='Apples 1kg' and p['stock_quantity']>=4), eligible[0])
        b = next((p for p in rows if p['name']=='Apple Juice 1L' and p['stock_quantity']>=4), eligible[1])
        category = next((c for c in RetrievalTools(isolated.database_path,None).categories() if c['name']=='Snacks'), {'category_id':a['category_id'],'name':a['category']})
        with connection(isolated.database_path) as conn:
            members = [dict(p) for p in conn.execute('SELECT product_id,name,calories_per_100,calorie_basis FROM product WHERE category_id=?',(category['category_id'],))]
        search = create_search_service(isolated, embeddings, vectors)
        cart = CartService(isolated.database_path)
        slot = {}
        calls = []
        def factory(current, service, owner):
            if not offline: return create_runner(current, service, owner)
            task = slot.get('task', {'query':'products','source':'sql'})
            retrieval_llm = RetrievalDecisions(task,slot.get('wanted',set()))
            retrieval = RetrievalAgent(current,RetrievalTools(current.database_path,service),retrieval_llm,OllamaRelevanceJudge(current,retrieval_llm))
            specialist = cart_runner(current,owner,ScriptedLLM([slot.get('cart',{'action':'view_cart'})]))
            return CustomerAgent(current,CustomerTools(retrieval,specialist),ScriptedLLM([
                slot['plan'],slot.get('reply',{'answer':'Scripted workflow answer.'})]))
        assistant = AssistantService(isolated,search,ConversationService(isolated),memory,factory)
        cid = None
        page = {'page':'shop'}
        recent = []
        orders = []
        before = {p['product_id']:stock(isolated,p['product_id']) for p in (a,b)}

        def chat(case_id, query, plan, validate, reply=None, decision=None, task=None, wanted=()):
            nonlocal cid,page,recent
            slot.clear(); slot.update(plan=plan,reply=reply or {'answer':'Scripted workflow answer.'},cart=decision or {'action':'view_cart'},task=task or {'query':query,'source':'sql'},wanted=set(wanted))
            def run():
                nonlocal cid,page,recent
                request = ChatRequest(query=query,conversation_id=cid,page_context={**page,'referenced_product_ids':recent})
                result = assistant.chat(1,request)
                cid = result['conversation_id']
                calls.append({'operation':'chat','input':{'query':query,'page':request.page_context.model_dump()},'output':result,'status':'ok'})
                if result.get('products'): recent = [p['product_id'] for p in result['products']][:10]
                for action in result.get('actions',[]):
                    if action.get('trigger')=='on_click': continue
                    if action['action']=='open_product': page={'page':'product','product_id':action['product_id']}
                    elif action['action']=='navigate': page={'page':action['page']}
                    elif action['action']=='apply_search':
                        page={'page':'shop','search':action.get('query',''),'category_id':action.get('category_id'), 'visible_product_ids':recent}
                return result
            start=len(calls)
            row=record_case(f'journey_{repetition}_{case_id}',query,run,
                lambda result:{'other_customer_cart_isolated':not cart.view(2)['items'],**validate(result)},calls)
            row['calls']=calls[start:]
            cases.append(row)
            return row.get('output',{})

        def quantities(): return {p['product_id']:p['quantity'] for p in cart.view(1)['items']}
        def action_is(result, action): return any(x['action']==action for x in result.get('actions',[]))
        task={'query':'apple products' if 'Apple' in a['name'] else a['name'],'source':'both',
              'catalog':{'product_ids':[a['product_id'],b['product_id']]}}
        chat('greeting','hi',{'steps':[]},lambda r:{'answer_present':bool(r['answer']),'no_mutation':not quantities()})
        chat('choices',f"Show {a['name']} and {b['name']} as choices; let me choose before opening one.",
             {'interaction':'view_product','steps':[],'actions':[{'action':'apply_search','query':task['query']}]},
             lambda r:{'both_cards':{a['product_id'],b['product_id']} <= {p['product_id'] for p in r.get('products',[])},
                       'no_random_open':not action_is(r,'open_product')},task=task,wanted=(a['product_id'],b['product_id']))
        chat('choose_product',f"Show {a['name']}",{'interaction':'view_product','actions':[{'action':'open_product','product_id':a['product_id']}]},
             lambda r:{'opens_requested':any(x['action']=='open_product' and x['product_id']==a['product_id'] and x.get('trigger')=='automatic' for x in r.get('actions',[]))})
        chat('add_reference','add it in the cart',{'interaction':'add_to_cart'},
             lambda r:{'cart_written':quantities()=={a['product_id']:1},'no_forced_cart_navigation':not any(x['action']=='navigate' and x.get('page')=='cart' and x.get('trigger')!='on_click' for x in r.get('actions',[]))},
             decision={'action':'update_cart','items':[{'product_id':a['product_id'],'quantity':1}]},reply={'answer':f"Added {a['name']} to your cart."})
        chat('quantity',f"Change {a['name']} quantity to 2",{'steps':['cart']},
             lambda r:{'absolute_quantity':quantities()=={a['product_id']:2},'stock_not_reserved':stock(isolated,a['product_id'])==before[a['product_id']]},
             decision={'action':'update_cart','items':[{'product_id':a['product_id'],'quantity':2}]})
        chat('excess_stock',f"Change {a['name']} quantity to {before[a['product_id']]+1}",{'steps':['cart']},
             lambda r:{'insufficient_stock_blocked':r.get('results',{}).get('cart',{}).get('status') in {'validation_failed','needs_clarification'},
                       'cart_preserved':quantities()=={a['product_id']:2},
                       'no_committed_update':not (r.get('results',{}).get('cart',{}).get('status')=='ok' and r.get('results',{}).get('cart',{}).get('action')=='update_cart')},
             decision={'action':'update_cart','items':[{'product_id':a['product_id'],'quantity':before[a['product_id']]+1}]},
             reply={'answer':'Added the products to your cart.'})
        chat('view_cart','show my cart',{'interaction':'view_cart','steps':['cart']},
             lambda r:{'cart_view_available':r.get('results',{}).get('cart',{}).get('output',{}).get('items')==cart.view(1)['items'] or any(x['action']=='navigate' and x.get('page')=='cart' and x.get('trigger')!='on_click' for x in r.get('actions',[]))},
             decision={'action':'view_cart'},reply={'answer':'Here is your cart.','actions':[{'action':'navigate','page':'cart'}]})
        chat('category_calories',f"Show calorie information for all {category['name']} products",
             {'steps':['retrieval'],'specialist_query':f"All {category['name']} products and their calories"},
             lambda r:{'whole_category_complete':r.get('results',{}).get('retrieval',{}).get('retrieval_ok') is True,
                       'all_category_names_in_answer':all(p['name'] in r.get('answer','') for p in members),
                       'all_category_cards':{p['product_id'] for p in members} <= {p['product_id'] for p in r.get('products',[])},
                       'calorie_values_retained':all('calories_per_100' in p and 'calorie_basis' in p for p in r.get('products',[]))},
             task={'query':f"{category['name']} calories",'source':'both','filters':{'category_id':category['category_id']},
                   'catalog':{'fields':['calories_per_100'],'all_matches':True}},wanted=[p['product_id'] for p in members])

        def checkout(number, product, quantity):
            prepared=chat(f'prepare_{number}','I want to checkout my cart',{'interaction':'checkout','steps':['cart']},
                lambda r:{'quote_ready':r.get('results',{}).get('cart',{}).get('output',{}).get('ready') is True,
                          'no_unconfirmed_order':len(cart.history(1))==number-1},decision={'action':'prepare_checkout'})
            token=prepared.get('results',{}).get('cart',{}).get('output',{}).get('confirmation_token')
            def confirm():
                if not token: raise ValueError('Checkout quote missing')
                body={'token':token,'confirmed':True,'payment_method':'cash_on_delivery','delivery_address':'Synthetic evaluation address'}
                first=cart.checkout(1,body); repeat=cart.checkout(1,body)
                orders.append(first['order']['order_id'])
                return {'order':first['order'],'already_completed_on_retry':repeat['already_completed']}
            if number == 1 and token:
                def unauthorized():
                    try:
                        cart.checkout(2,{'token':token,'confirmed':True,'payment_method':'cash_on_delivery','delivery_address':'Synthetic other address'})
                    except ServiceError as error:
                        return {'status':error.status_code}
                    return {'status':200}
                cases.append(record_case(f'journey_{repetition}_cross_customer_checkout','Other synthetic customer attempts quote confirmation',unauthorized,
                    lambda r:{'ownership_checked':r['status']==404,'no_other_order':not cart.history(2)},[]))
            cases.append(record_case(f'journey_{repetition}_confirm_{number}','Explicit confirmation form and retry',confirm,
                lambda r:{'pending_order':r['order']['status']=='pending','unpaid_cod':r['order']['payment_status']=='unpaid',
                          'idempotent_checkout':r['already_completed_on_retry'],'stock_deducted_once':stock(isolated,product['product_id'])==before[product['product_id']]-quantity,
                          'cart_empty':not quantities(),'other_customer_orders_isolated':not cart.history(2)},[]))
        checkout(1,a,2)
        chat('history','show my previous orders',{'steps':['cart']},
             lambda r:{'one_owned_order':len(r.get('results',{}).get('cart',{}).get('output',[]))==1},decision={'action':'order_history'})
        if orders:
            chat('status',f"What is the status of order {orders[0]}?",{'steps':['cart']},
                lambda r:{'pending_not_shipped':r.get('results',{}).get('cart',{}).get('output',{}).get('status')=='pending'},
                decision={'action':'order_status','order_id':orders[0]})
            chat('early_review',f"Rate product {a['product_id']} in order {orders[0]} 5 stars",
                 {'steps':['cart']},lambda r:{'undelivered_review_blocked':not cart.order(1,orders[0])['reviews'] and (r.get('results',{}).get('cart',{}).get('status')=='validation_failed' or bool(re.search(r"\b(?:only|cannot|can't|not|unable)\b.*\b(?:delivered|delivery|rating|rate|review)\b",r['answer'],re.I|re.S)))},
                 decision={'action':'review_product','order_id':orders[0],'product_id':a['product_id'],'rating':5})
        # A second order in the same conversation exercises stale references and cart clearing.
        chat('second_product',f"Show {b['name']}",{'interaction':'view_product','actions':[{'action':'open_product','product_id':b['product_id']}]},
             lambda r:{'opens_second':any(x['action']=='open_product' and x['product_id']==b['product_id'] and x.get('trigger')=='automatic' for x in r.get('actions',[]))},
             task={'query':b['name'],'source':'both','catalog':{'product_ids':[b['product_id']]}},wanted=[b['product_id']])
        chat('second_add','add it to the cart',{'interaction':'add_to_cart'},
             lambda r:{'only_second_product':quantities()=={b['product_id']:1}},
             decision={'action':'update_cart','items':[{'product_id':b['product_id'],'quantity':1}]},reply={'answer':f"Added {b['name']} to your cart."})
        checkout(2,b,1)
        # Durable SQL order history contains two synthetic orders after one conversation.
        chat('two_orders','why are my two orders pending?',{'steps':['cart']},
             lambda r:{'two_owned_orders':len(r.get('results',{}).get('cart',{}).get('output',[]))==2,
                       'all_pending':all(o['status']=='pending' for o in cart.history(1)),
                       'cod_does_not_block_fulfillment':'does not prevent fulfillment' in r.get('answer','')},decision={'action':'order_history'})
    return cases


def main():
    parser=argparse.ArgumentParser(description='Repeated isolated shopping conversations through the customer/retrieval/cart agents')
    parser.add_argument('--offline',action='store_true',help='Scripted model decisions and test vectors; not model quality')
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not 1 <= args.repetitions <= 20: parser.error('--repetitions must be between 1 and 20')
    output=args.output or PROJECT_ROOT/'data/evaluation_reports'/('shopping_journeys_offline.json' if args.offline else 'shopping_journeys_live.json')
    report={'mode':'offline_scripted' if args.offline else 'live_ollama_hybrid_sql','cases':[],
            'isolation':'Catalog-only SQL clone and synthetic customers per journey; no real orders or shared memory writes',
            'limitations':'Offline model decisions and constant embeddings test workflow only. Browser DOM is tested separately; no visual browser evaluation. Live factuality requires review.',
            'repetitions':args.repetitions}
    vectors=None
    try:
        settings=get_settings()
        if args.offline:
            embeddings=OfflineEmbeddings()
            vectors=QdrantProductIndex('','journey_products',2,'test-embedding',client=QdrantClient(':memory:'))
            with connection(settings.database_path) as conn:
                for p in list_products(conn): vectors.upsert(p,[1.,0.],'test')
        else:
            for service,url in [('ollama',settings.ollama_base_url),('qdrant',settings.qdrant_url)]:
                try: httpx.get(url,timeout=5).raise_for_status()
                except Exception as exc:
                    report['unavailable_service']=service
                    raise exc
            embeddings=embedding_client(settings); vectors=vector_index(settings)
        for repetition in range(1,args.repetitions+1):
            report['cases'].extend(evaluate_journey(settings,repetition,args.offline,embeddings,vectors))
    except Exception as exc:
        report['setup_error_type']=type(exc).__name__
    finally:
        if vectors: vectors.close()
    return save_report(report,output)


if __name__=='__main__': raise SystemExit(main())
