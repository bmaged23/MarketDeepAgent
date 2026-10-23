import json
from types import SimpleNamespace
import pytest
from app.config import Settings
from app.database.connection import connection
from app.agents.cart.agent import create_runner, create_agent
from app.agents.customer.agent import CustomerAgent
from app.agents.customer.tools import CustomerTools


class LLM:
    def __init__(self, replies):
        self.replies, self.calls = iter(replies), []
    def chat(self, messages):
        self.calls.append(messages)
        return {"message": {"content": json.dumps(next(self.replies))}}


@pytest.fixture
def customer(products):
    db, _, items = products
    with connection(db, write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email) VALUES('Test','Customer','agent@example.test')")
    return Settings(_env_file=None, database_path=db), items


def test_agent_changes_only_resolved_products(customer):
    settings, items = customer
    llm = LLM([{"action": "update_cart", "items": [{"product_id": items[0]["product_id"], "quantity": 2}]}])
    agent = create_runner(settings, 1, llm)
    result = agent.run("Add two teas")
    assert result["status"] == "needs_retrieval"
    assert not agent.tools.view_cart()["items"]
    llm = LLM([{"action": "update_cart", "items": [{"product_id": items[0]["product_id"], "quantity": 2}]}])
    agent = create_runner(settings, 1, llm)
    result = agent.run("Add two teas", evidence={"sections": [{"chunks": [{"approval": 1, "product": items[0]}]}]})
    assert result["output"]["total"] == 170
    assert "complete_order" not in create_agent(settings, 1).tools


def test_agent_returns_validation_failure_not_success(customer):
    settings, items = customer
    llm = LLM([{"action": "update_cart", "items": [{"product_id": items[1]["product_id"], "quantity": 1}]}])
    agent = create_runner(settings, 1, llm)
    result = agent.run("Add coffee", evidence={"sections": [{"chunks": [{"approval": 1, "product": items[1]}]}]})
    assert result["status"] == "validation_failed"
    assert not agent.tools.view_cart()["items"]


def test_coordinator_orders_retrieval_before_cart(customer):
    settings, _ = customer
    calls = []
    class Retrieval:
        def run(self, query):
            calls.append("retrieval")
            return {"sections": []}
    class Cart:
        def run(self, query, evidence=None, history=None):
            calls.append("cart")
            assert evidence == {"sections": []}
            return {"status": "ok", "output": {"confirmation_token": "private-token", "ready": True}}
    llm = LLM([{"steps": ["cart", "retrieval"]}, {"answer": "Please confirm checkout."}])
    agent = CustomerAgent(settings, CustomerTools(Retrieval(), Cart()), llm)
    result = agent.run("Find tea and add it")
    assert calls == ["retrieval", "cart"]
    assert result["answer"] == "Please confirm checkout."
    assert "private-token" not in llm.calls[-1][1]["content"]
    assert result["results"]["cart"]["output"]["confirmation_token"] == "private-token"


def test_coordinator_retries_cart_after_product_resolution(customer):
    settings, _ = customer
    class Retrieval:
        def run(self, query): return {"sections": []}
    class Cart:
        def __init__(self): self.calls = 0
        def run(self, query, evidence=None, history=None):
            self.calls += 1
            return {"status": "needs_retrieval"} if evidence is None else {"status": "ok"}
    cart = Cart()
    llm = LLM([{"steps": ["cart"]}, {"answer": "Cart updated."}])
    result = CustomerAgent(settings, CustomerTools(Retrieval(), cart), llm).run("Add tea")
    assert cart.calls == 2
    assert result["results"]["cart"]["status"] == "ok"


def test_review_action_requires_specific_purchased_product(customer):
    settings, items = customer
    llm = LLM([{"action": "review_product", "order_id": 999, "product_id": items[0]["product_id"], "rating": 5, "comment": "Nice"}])
    result = create_runner(settings, 1, llm).run("Rate my tea five stars")
    assert result["status"] == "validation_failed"


def test_customer_explicit_confirmation_uses_cart_service(customer):
    settings, items = customer
    cart = create_runner(settings, 1, LLM([]))
    cart.tools.update_cart([{"product_id": items[0]["product_id"], "quantity": 1}])
    token = cart.tools.prepare_checkout()["confirmation_token"]
    agent = CustomerAgent(settings, CustomerTools(None, cart), LLM([]))
    result = agent.confirm_order({"token": token, "confirmed": True, "payment_method": "cash_on_delivery", "delivery_address": "Test delivery address"})
    assert result["results"]["cart"]["output"]["order"]["payment_status"] == "unpaid"
    assert "Payment is due on delivery" in result["answer"]
    assert "$85.00" in result["answer"]


def test_show_recent_product_opens_it_without_retrieval_or_second_model_call(customer):
    settings, items = customer
    class Specialists:
        def retrieve_products(self, query): raise AssertionError('Known product should not be retrieved again')
        def manage_cart(self, *args, **kwargs): raise AssertionError('Opening a product must not touch cart')
    llm = LLM([{'steps': [], 'actions': [{'action':'open_product','product_id':items[0]['product_id']}]}])
    result = CustomerAgent(settings, Specialists(), llm).run('can you show it to me', context={'referenced_products':[items[0]]})
    assert result['actions'][0]['action']=='open_product'
    assert result['actions'][0]['product_id']==items[0]['product_id']
    assert items[0]['name'] in result['answer']
    assert len(llm.calls)==1
    assert result['results']=={}


def test_unverified_navigation_product_is_resolved_before_opening(customer):
    settings, items = customer
    class Specialists:
        def __init__(self): self.calls=[]
        def retrieve_products(self, query):
            self.calls.append(query)
            return {'sections':[{'query':'tea','chunks':[{'approval':1,'product':items[0]}]}]}
    tools=Specialists()
    llm=LLM([{'steps':[],'actions':[{'action':'open_product','product_id':99999}]},
             {'answer':'Here is the tea.','actions':[{'action':'open_product','product_id':items[0]['product_id']}]}])
    result=CustomerAgent(settings,tools,llm).run('Show the tea',context={})
    assert tools.calls==['Show the tea']
    assert result['actions'][0]['product_id']==items[0]['product_id']


def test_ui_page_navigation_does_not_call_cart(customer):
    settings,_=customer
    llm=LLM([{'steps':[],'actions':[{'action':'navigate','page':'orders'}]}])
    result=CustomerAgent(settings,None,llm).run('Take me to my orders')
    assert result['actions'][0]['page']=='orders' and len(llm.calls)==1


def test_model_repair_identifies_invalid_action_field_without_raw_content():
    from app.utils.llm_json import ask_json, StructuredResponseError
    from app.agents.customer.schemas import CustomerPlan
    bad={'steps':['secret-raw-model-text']}
    llm=LLM([bad,{'steps':[],'actions':[{'action':'navigate','page':'cart'}]}])
    plan=ask_json(llm,'Plan UI',{},CustomerPlan,retries=1)
    assert plan.actions[0].page=='cart'
    repair=llm.calls[-1][-1]['content']
    assert 'steps.0' in repair and 'literal_error' in repair
    assert 'secret-raw-model-text' not in repair
    with pytest.raises(StructuredResponseError,match='CustomerPlan response validation failed') as exc:
        ask_json(LLM([bad]),'Plan UI',{},CustomerPlan,retries=0)
    assert 'secret-raw-model-text' not in str(exc.value)


def test_product_question_offers_view_without_opening_or_adding(customer):
    settings,items=customer
    class Retrieval:
        def run(self,query): return {'sections':[{'query':query,'chunks':[{'approval':1,'product':items[0]}]}]}
    llm=LLM([{'interaction':'answer','steps':['retrieval']},
             {'answer':'This tea costs $85.00. Would you like to view it?', 'actions':[{'action':'open_product','product_id':items[0]['product_id']}]}])
    result=CustomerAgent(settings,CustomerTools(Retrieval(),None),llm).run('Tell me about the tea')
    assert result['actions'][0]['trigger']=='on_click'
    assert 'cart' not in result['results']


def test_explicit_view_overrides_optional_suggestion_trigger(customer):
    settings,items=customer
    llm=LLM([{'interaction':'view_product','steps':[], 'actions':[{'action':'open_product','product_id':items[0]['product_id'],'trigger':'on_click'}]}])
    result=CustomerAgent(settings,None,llm).run('Show me the tea',context={'referenced_products':[items[0]]})
    assert result['actions'][0]['trigger']=='automatic' and len(llm.calls)==1


def test_cart_update_does_not_offer_navigation_when_cart_is_already_open():
    from app.agents.customer.schemas import CustomerPlan
    from app.application_guide.schemas import UIAction
    actions=CustomerAgent.interaction_actions(
        CustomerPlan(interaction='add_to_cart'),[UIAction(action='navigate',page='cart')],
        {'cart':{'status':'ok','action':'update_cart'}}, {'page_context':{'page':'cart'}})
    assert actions==[]


def test_selected_product_add_executes_sql_even_if_plan_omits_cart(customer):
    settings, items = customer
    cart = create_runner(settings, 1, LLM([{"action": "update_cart", "items": [{"product_id": items[0]["product_id"], "quantity": 1}]}]))
    class Retrieval:
        def run(self, query): raise AssertionError("Known SQL product needs no retrieval")
    llm = LLM([{"interaction": "add_to_cart", "steps": []}, {"answer": "Tea is already in your cart."}])
    result = CustomerAgent(settings, CustomerTools(Retrieval(), cart), llm).run(
        "add it in the cart", context={"selected_product": items[0]})
    assert result["results"]["cart"]["action"] == "update_cart"
    assert cart.tools.view_cart()["items"][0]["product_id"] == items[0]["product_id"]
    assert cart.tools.view_cart()["items"][0]["quantity"] == 1
    assert "already" not in result["answer"]
    assert items[0]["name"] in result["answer"]
    assert "× 1" in result["answer"]


def test_followup_yes_uses_referenced_product_and_writes_cart(customer):
    settings, items = customer
    cart = create_runner(settings, 1, LLM([{"action": "update_cart", "items": [{"product_id": items[0]["product_id"], "quantity": 1}]}]))
    llm = LLM([{"interaction": "add_to_cart", "specialist_query": "Add one tea"}, {"answer": "Tea added."}])
    result = CustomerAgent(settings, CustomerTools(None, cart), llm).run("yes",
        history=[{"role": "assistant", "content": "Add one tea?"}],
        context={"referenced_products": [items[0]]})
    assert result["results"]["cart"]["status"] == "ok"
    assert len(cart.tools.view_cart()["items"]) == 1


def test_unsuccessful_add_cannot_claim_success(customer):
    settings, items = customer
    cart = create_runner(settings, 1, LLM([{"action": "view_cart"}]))
    llm = LLM([{"interaction": "add_to_cart"}, {"answer": "Tea added to your cart."}])
    result = CustomerAgent(settings, CustomerTools(None, cart), llm).run("Add it",
        context={"selected_product": items[0]})
    assert result["answer"].startswith("No product was added")
    assert not cart.tools.view_cart()["items"]


def test_history_cannot_substitute_for_a_cart_write(customer):
    settings, _ = customer
    llm = LLM([{"steps": []}, {"answer": "The tea has been added to your cart."}])
    result = CustomerAgent(settings, None, llm).run("yes")
    assert result["answer"].startswith("No product was added")


def test_product_view_search_resolves_match_and_opens_even_if_reply_omits_action(customer):
    settings,items=customer
    class Retrieval:
        def run(self,query):
            return {'sections':[{'query':query,'chunks':[{'approval':1,'product':items[0]}]}]}
    llm=LLM([{'interaction':'view_product','steps':[],
              'actions':[{'action':'apply_search','query':'tea'}]},
             {'answer':'Showing matching products in the shop.'}])
    result=CustomerAgent(settings,CustomerTools(Retrieval(),None),llm).run('Show me the tea')
    assert result['actions']==[{'action':'open_product','trigger':'automatic','page':None,
                               'product_id':items[0]['product_id'],'category_id':None,'query':''}]
    assert result['answer']=='Opening Black Tea.'
    assert result['results']['retrieval']['sections'][0]['chunks'][0]['product']==items[0]


def test_multiple_actual_view_matches_keep_cards_and_do_not_open_random_product(customer):
    settings,items=customer
    class Retrieval:
        def run(self,query):
            return {'sections':[{'query':query,'chunks':[{'approval':1,'product':p} for p in items[:2]]}]}
    llm=LLM([{'interaction':'view_product','steps':['retrieval']},
             {'answer':'Opening tea.', 'actions':[{'action':'open_product','product_id':items[0]['product_id']}]}])
    result=CustomerAgent(settings,CustomerTools(Retrieval(),None),llm).run('Show me a beverage')
    assert not result['actions']
    assert 'Black Tea' in result['answer'] and 'Coffee' in result['answer']
    assert len(result['results']['retrieval']['sections'][0]['chunks'])==2


def test_followup_can_open_single_verified_visible_product_without_retrieval(customer):
    settings,items=customer
    llm=LLM([{'interaction':'view_product','steps':[],
              'actions':[{'action':'open_product','product_id':items[0]['product_id']}]}])
    result=CustomerAgent(settings,None,llm).run('okay show it to me',context={
        'page_context':{'page':'shop','search':'tea'},'visible_products':[items[0]]})
    assert result['answer']=='Opening Black Tea.'
    assert result['actions'][0]['product_id']==items[0]['product_id']


@pytest.mark.parametrize('failure',['network','invalid_json'])
def test_successful_cart_write_has_receipt_if_final_answer_model_fails(customer,failure):
    import httpx
    settings,items=customer
    cart=create_runner(settings,1,LLM([{'action':'update_cart','items':[{'product_id':items[0]['product_id'],'quantity':1}]}]))
    class FailingAnswer:
        def __init__(self):self.calls=0
        def chat(self,messages):
            self.calls+=1
            if self.calls==1:return {'message':{'content':json.dumps({'interaction':'add_to_cart'})}}
            if failure=='network':raise httpx.ConnectError('synthetic network failure')
            return {'message':{'content':'invalid JSON'}}
    result=CustomerAgent(settings,CustomerTools(None,cart),FailingAnswer()).run('add it',context={'selected_product':items[0]})
    assert result['reply_recovered'] is True
    assert 'Black Tea × 1' in result['answer'] and '$85.00' in result['answer']
    assert cart.tools.view_cart()['items'][0]['quantity']==1
    assert result['actions'][0]['page']=='cart' and result['actions'][0]['trigger']=='on_click'


def test_checkout_cannot_replay_previous_addition(customer):
    settings,items=customer
    cart=create_runner(settings,1,LLM([]))
    cart.tools.update_cart([{'product_id':items[0]['product_id'],'quantity':1}])
    class NoRetrieval:
        def run(self,query):raise AssertionError('Checkout must not search products')
    llm=LLM([{'interaction':'view_product','steps':['retrieval'],'specialist_query':'add another tea'},
             {'answer':'Review your checkout quote.'}])
    result=CustomerAgent(settings,CustomerTools(NoRetrieval(),cart),llm).run('I want to checkout my cart',
        history=[{'role':'user','content':'add it to the cart'}],context={'selected_product':items[0]})
    assert result['results']['cart']['action']=='prepare_checkout'
    assert result['results']['cart']['output']['ready']
    assert cart.tools.view_cart()['items'][0]['quantity']==1
    assert json.loads(llm.calls[-1][-1]['content'])=={'request':'I want to checkout my cart'}


def test_order_question_uses_fresh_sql_not_product_catalog(customer):
    settings,items=customer
    cart=create_runner(settings,1,LLM([]))
    cart.tools.update_cart([{'product_id':items[0]['product_id'],'quantity':1}])
    token=cart.tools.prepare_checkout()['confirmation_token']
    order=cart.tools.complete_order({'token':token,'confirmed':True,'payment_method':'cash_on_delivery','delivery_address':'Synthetic address'})['order']
    class NoRetrieval:
        def run(self,query):raise AssertionError('Order status is not a product search')
    llm=LLM([{'steps':['retrieval'],'specialist_query':'product calories'}, {'answer':'Your order is pending.'}])
    result=CustomerAgent(settings,CustomerTools(NoRetrieval(),cart),llm).run(f"What is the status of order {order['order_id']}?")
    assert result['results']['cart']['action']=='order_status'
    assert result['results']['cart']['output']['status']=='pending'
    assert not cart.tools.view_cart()['items']


def test_explicit_product_view_overrides_stale_review_answer(customer):
    settings,items=customer
    class Retrieval:
        def run(self,query):
            assert query=='Show Black Tea'
            return {'sections':[{'query':query,'chunks':[{'approval':1,'product':items[0]}]}]}
    llm=LLM([{'interaction':'answer','steps':[],'specialist_query':'review my order',
              'actions':[{'action':'apply_search','query':'Black Tea','trigger':'on_click'}]},
             {'answer':'You cannot review before delivery.'}])
    result=CustomerAgent(settings,CustomerTools(Retrieval(),None),llm).run('Show Black Tea')
    assert result['answer']=='Opening Black Tea.' and result['actions'][0]['trigger']=='automatic'


def test_cart_view_reads_snapshot_without_a_second_answer_call(customer):
    settings,items=customer
    cart=create_runner(settings,1,LLM([]))
    cart.tools.update_cart([{'product_id':items[0]['product_id'],'quantity':2}])
    llm=LLM([{'steps':[],'actions':[{'action':'navigate','page':'cart'}]}])
    result=CustomerAgent(settings,CustomerTools(None,cart),llm).run('show my cart')
    assert result['results']['cart']['output']['items']==cart.tools.view_cart()['items']
    assert '$170.00' in result['answer'] and len(llm.calls)==1
    assert result['actions'][0]['trigger']=='automatic'


def test_explicit_read_survives_invalid_planner_json(customer):
    settings,_=customer
    cart=create_runner(settings,1,LLM([]))
    class BadPlanner:
        def chat(self,messages):return {'message':{'content':'invalid'}}
    result=CustomerAgent(settings,CustomerTools(None,cart),BadPlanner()).run('show my cart')
    assert result['results']['cart']['action']=='view_cart'
    assert result['answer']=='Your cart is empty.'
    assert result['actions'][0]['page']=='cart'


@pytest.mark.parametrize('query',['do not checkout my cart','how do I checkout?',
    'show the calorie information for this product','show nutritional details',
    'Take me to my orders'])
def test_explicit_routing_leaves_explanations_negations_and_page_navigation_to_model(query):
    from app.utils.shopping_intent import explicit_shopping_intent
    assert explicit_shopping_intent(query) is None


def test_pending_cod_reply_cannot_claim_payment_blocks_shipping(customer):
    settings, items = customer
    cart = create_runner(settings, 1, LLM([]))
    cart.tools.update_cart([{'product_id': items[0]['product_id'], 'quantity': 1}])
    token = cart.tools.prepare_checkout()['confirmation_token']
    order = cart.tools.complete_order({'token': token, 'confirmed': True,
        'payment_method': 'cash_on_delivery', 'delivery_address': 'Synthetic address'})['order']
    llm = LLM([{'steps': ['cart']}, {'answer': 'Shipping cannot start until the courier collects payment.'}])
    result = CustomerAgent(settings, CustomerTools(None, cart), llm).run('Why are my orders pending?')
    assert str(order['order_id']) in result['answer']
    assert 'waiting to be processed and shipped' in result['answer']
    assert 'does not prevent fulfillment' in result['answer']
    assert 'cannot start' not in result['answer']


def test_exhaustive_calorie_reply_preserves_all_approved_facts():
    from app.utils.shopping_replies import full_calorie_reply
    chunks = [{'approval': 1, 'product': {'product_id': i, 'name': f'Snack {i}',
        'calories_per_100': i * 10, 'calorie_basis': '100g', 'calorie_status': 'estimated',
        'calorie_notes': 'Dry product.'}} for i in range(12)]
    result = {'retrieval_ok': True, 'sections': [{'selection': {'all_matches': True}, 'chunks': chunks}]}
    answer = full_calorie_reply(result)
    assert all(f'**Snack {i}**' in answer for i in range(12))
    assert '0 kcal' in answer and '110 kcal' in answer
    assert 'Dry product.' in answer
    result['retrieval_ok'] = False
    assert full_calorie_reply(result) is None


@pytest.mark.parametrize('page,offer_removed', [('cart', True), ('shop', False)])
def test_product_answer_does_not_offer_already_visible_cart(customer, page, offer_removed):
    settings, items = customer
    class Retrieval:
        def run(self, query):
            return {'sections': [{'query': query, 'chunks': [{'approval': 1, 'product': items[0]}]}]}
    llm = LLM([{'steps': ['retrieval']},
        {'answer': 'The recorded calorie information is shown above. Would you like me to show you your cart?'}])
    result = CustomerAgent(settings, CustomerTools(Retrieval(), None), llm).run(
        'Tell me about the product calories.', context={'page_context': {'page': page}})
    assert 'recorded calorie information' in result['answer']
    assert ('show you your cart' not in result['answer']) == offer_removed


def test_prepare_checkout_with_placement_prohibition_is_only_a_quote(customer):
    from app.utils.shopping_intent import explicit_shopping_intent
    query='Prepare checkout, but do not place the order until I confirm using the checkout form.'
    assert explicit_shopping_intent(query)=='prepare_checkout'
    assert explicit_shopping_intent('Do not prepare checkout') is None
    settings,items=customer
    cart=create_runner(settings,1,LLM([]))
    cart.tools.update_cart([{'product_id':items[0]['product_id'],'quantity':1}])
    result=cart.run(query)
    assert result['action']=='prepare_checkout' and result['output']['ready']
    assert not cart.tools.order_history()


def test_customer_passes_original_cart_action_when_search_rewrite_drops_it(customer):
    settings,items=customer
    cart=create_runner(settings,1,LLM([{'action':'update_cart','items':[{'product_id':items[0]['product_id'],'quantity':2}]}]))
    calls=[]
    original=cart.run
    def recorded(query,**kwargs):
        calls.append(query);return original(query,**kwargs)
    cart.run=recorded
    model=LLM([{'steps':['cart'],'specialist_query':'Product details only'}, {'answer':'Done'}])
    query='Add 2 of this product as well.'
    result=CustomerAgent(settings,CustomerTools(None,cart),model).run(query,context={'selected_product':items[0]})
    assert calls==[query]
    assert result['results']['cart']['output']['items'][0]['quantity']==2


def test_review_order_status_is_not_mistaken_for_a_product_rating(customer):
    settings,items=customer
    cart=create_runner(settings,1,LLM([]))
    cart.tools.update_cart([{'product_id':items[0]['product_id'],'quantity':1}])
    quote=cart.tools.prepare_checkout()
    order=cart.tools.complete_order({'token':quote['confirmation_token'],'confirmed':True,
        'payment_method':'cash_on_delivery','delivery_address':'Synthetic address'})['order']
    result=cart.run(f"Review the status of my order {order['order_id']}")
    assert result['action']=='order_status' and result['status']=='ok'
