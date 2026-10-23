"""Freeze catalog-first evaluation inputs before running any model."""
import hashlib,json,random
from pathlib import Path
from app.config import get_settings,PROJECT_ROOT
from app.database.connection import connection
from app.products.queries import list_products
from app.utils.agent_evaluation import evaluation_catalog,cart_scenario
from app.agents.cart.evaluation import CASES as CART_CASES
from app.agents.customer.evaluation import CASES as CUSTOMER_CASES

VERSION='market-agents-v1'
def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def snapshot(database):
    with connection(database) as c:
        return {t:[dict(r) for r in c.execute('SELECT * FROM '+t)] for t in
                ['product','customer_cart','customer_cart_items','orders','verified_product_reviews']}
def build(settings):
    with connection(settings.database_path) as c:
        catalog=list_products(c)
        categories=[dict(r) for r in c.execute('SELECT category_id,name FROM category ORDER BY category_id')]
    catalog=sorted(catalog,key=lambda p:p['product_id'])
    eligible=[p for p in catalog if p['stock_quantity']>=4]
    rng=random.Random(20261023);rng.shuffle(eligible)
    cases=[]
    # Thirty reference-labelled retrieval cases, preserved from the existing source-reviewed starter set.
    old=json.loads((PROJECT_ROOT/'evaluation/datasets/search-starter-v1.json').read_text())
    for c in old[:30]:
        gold=[p for p in catalog if p['name'] in c['relevant_product_names']]
        assert len(gold)==len(c['relevant_product_names'])
        cases.append({'case_id':'retrieval-'+str(len(cases)+1).zfill(3),'scope':'retrieval',
            'query':c.get('agent_expectations',{}).get('user_message',c['query']),
            'constraints':c.get('filters',{}),'query_type':c['query_type'],
            'relevant_product_ids':[p['product_id'] for p in gold],
            'reference_evidence':gold,'reference_answer_facts':[{k:p[k] for k in ['product_id','name','price','stock_quantity','category','calories_per_100','calorie_basis','calorie_status']} for p in gold],
            'oracle_sql':{'query':'SELECT product_id,name,price,stock_quantity,category_id FROM product WHERE product_id IN ('+','.join('?' for p in gold)+') ORDER BY product_id','parameters':[p['product_id'] for p in gold]},
            'forbidden':['invented product facts','cart mutation','order placement'],
            'label_limitations':'Positive starter relevance labels are not exhaustive or independently human-adjudicated.'})
    for i in range(25):
        base=CART_CASES[i%len(CART_CASES)]
        with evaluation_catalog(settings) as (s,rows,products):
            query,decision,evidence,_=cart_scenario(s,products,base)
            if i>=len(CART_CASES):query='Please help with this shopping request: '+query
            initial=snapshot(s.database_path)
            expected={p['product_id']:p['quantity'] for p in initial['customer_cart_items'] if p['person_id']==1}
            if decision['action']=='update_cart':
                for p in decision['items']:
                    if p['quantity']:expected[p['product_id']]=p['quantity']
                    else:expected.pop(p['product_id'],None)
            if decision['action']=='clear_cart':expected={}
            cases.append({'case_id':f'cart-{i+1:03}','scope':'cart','base_case':base,'query':query,
                'initial_state':initial,'expected_decision':decision,'reference_evidence':evidence,
                'expected_cart':{str(k):v for k,v in expected.items()},
                'reference_answer_facts':{'operation':decision['action'],'order_must_not_be_created':True},
                'forbidden':['stock deduction','unconfirmed orders','cross-customer access']})
    for i in range(25):
        base=CUSTOMER_CASES[i%len(CUSTOMER_CASES)]
        with evaluation_catalog(settings) as (s,rows,products):
            p=products[0]
            if base in {'greeting','product_lookup'}:
                query='Hello!' if base=='greeting' else f"Find {p['name']} and tell me its price."
                decision=None;steps=[] if base=='greeting' else ['retrieval']
            else:
                mapped={'view_cart':'view_empty','confirmed_checkout':'prepare_checkout'}.get(base,base)
                query,decision,_,_=cart_scenario(s,products,mapped)
                steps=['retrieval','cart'] if base=='add_products' else ['cart']
            if i>=len(CUSTOMER_CASES):query=('Could you help me? ' if i<20 else 'For my current shopping session: ')+query
            cases.append({'case_id':f'customer-{i+1:03}','scope':'customer','base_case':base,'query':query,
                'initial_state':snapshot(s.database_path),'expected_specialists':steps,
                'expected_cart_decision':decision,'reference_evidence':products,
                'reference_answer_facts':{'request':query,'allowed_specialists':steps,'checkout_requires_separate_confirmation':True},
                'forbidden':['invented product facts','cross-customer access','checkout through chat alone']})
    for i in range(20):
        a,b=eligible[2*i],eligible[2*i+1]
        aq=1+i%2;newq=aq+1;bq=1
        turns=[
            {'query':f"Find {a['name']} and {b['name']}; tell me their prices without adding anything.",'expected_cart':{},'expected_products':[a['product_id'],b['product_id']]},
            {'query':f"Add {aq} of {a['name']} to my cart.",'expected_cart':{str(a['product_id']):aq}},
            {'query':f"Actually change the quantity of {a['name']} to {newq}.",'expected_cart':{str(a['product_id']):newq}},
            {'query':f"Add {bq} of {b['name']} as well.",'expected_cart':{str(a['product_id']):newq,str(b['product_id']):bq}},
            {'query':'Show my cart and its total.','expected_cart':{str(a['product_id']):newq,str(b['product_id']):bq}},
            {'query':'Prepare checkout, but do not place the order until I confirm using the checkout form.','expected_cart':{str(a['product_id']):newq,str(b['product_id']):bq},'expected_quote':True}]
        cases.append({'case_id':f'journey-{i+1:03}','scope':'journey','turns':turns,
            'reference_evidence':[a,b],
            'reference_answer_facts':{'a_name':a['name'],'a_price':a['price'],'b_name':b['name'],'b_price':b['price'],'expected_final_quantities':{str(a['product_id']):newq,str(b['product_id']):bq},'expected_total':round(newq*a['price']+bq*b['price'],2)},
            'post_chat_actions':['submit explicit checkout confirmation','repeat identical confirmation','attempt other-customer order lookup'],
            'forbidden':['stock deduction before form confirmation','duplicate checkout','cross-customer access']})
    assert len(cases)==100
    return catalog,categories,cases

def main():
    catalog,categories,cases=build(get_settings())
    target=PROJECT_ROOT/'evaluation/datasets';target.mkdir(parents=True,exist_ok=True)
    payload=''.join(dump(c)+'\n' for c in cases)
    (target/'market-agents-v1.jsonl').write_text(payload)
    catalog_text=dump({'products':catalog,'categories':categories})+'\n'
    (target/'catalog-v1.json').write_text(catalog_text)
    manifest={'version':VERSION,'seed':20261023,'cases':100,'counts':{s:sum(c['scope']==s for c in cases) for s in ['retrieval','cart','customer','journey']},
        'dataset_sha256':hashlib.sha256(payload.encode()).hexdigest(),'catalog_sha256':hashlib.sha256(catalog_text.encode()).hexdigest(),
        'embedding_model':'BAAI/bge-large-en-v1.5','embedding_revision':get_settings().embedding_revision,
        'provenance':'Existing starter retrieval labels plus mechanically frozen synthetic workflow expectations from the seeded SQL catalog; not real shoppers or independent human gold.',
        'split':'Exposed regression set; no untouched held-out accuracy claim.',
        'reference_policy':'Freeze before live evaluation; product_id is stable evidence identity, runtime chunk labels are not gold. SQL rows/constraints and business state are checked independently of prose.'}
    (target/'market-agents-v1.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
