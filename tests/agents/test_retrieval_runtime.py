import json
import pytest
import httpx
from app.config import Settings
from app.agents.retrieval.agent import RetrievalAgent
from app.agents.retrieval.tools import RetrievalTools
from app.model_clients.jev import JevClient
from app.utils.llm_json import ask_json, StructuredResponseError
from app.agents.retrieval.schemas import RetrievalPlan


class ScriptedLLM:
    def __init__(self, replies):
        self.replies, self.calls = iter(replies), []

    def chat(self, messages):
        self.calls.append(messages)
        reply = next(self.replies)
        return {"message": {"content": json.dumps(reply) if not isinstance(reply,str) else reply}}


class Judge:
    def __init__(self, batches):
        self.batches, self.calls = iter(batches), []

    def grade(self, query, chunks):
        self.calls.append(chunks)
        return {'model':'test-judge','usage':{},'decisions':[
            {'approval':label,'probability':float(label)} for label in next(self.batches)]}


class Search:
    def __init__(self, items):
        self.items, self.calls = items, []

    def search(self, query, filters, limit):
        self.calls.append((query,filters.model_dump(),limit))
        return {'degraded':False,'results':[
            {'product':dict(p),'score':1,'sources':['bm25','vector']} for p in self.items]}


def runner(products, replies, grades, **options):
    database,_,items = products
    settings=Settings(_env_file=None,database_path=database,**options)
    llm,judge,search = ScriptedLLM(replies),Judge(grades),Search(items)
    return RetrievalAgent(settings,RetrievalTools(database,search),llm,judge),llm,judge,search


def plan(*queries):
    return {'rewritten_query':'tea and bread','queries':[{'query':query} for query in queries]}


def coverage(done=False,queries=()):
    return {'retrieval_ok':done,'followup_queries':[{'query':query} for query in queries],
            'missing_information':[] if done else ['bread']}


def test_only_binary_approved_sql_chunks_enter_grouped_output(products):
    agent,llm,judge,search=runner(products,[plan('tea'),coverage(True)],[[1,0,0]])
    result=agent.run('find tea')
    assert result['retrieval_ok'] and result['status']=='done'
    assert len(result['sections'])==1
    assert [c['product']['name'] for c in result['sections'][0]['chunks']]==['Black Tea']
    assert result['context'].startswith('Query: tea\n')
    assert 'Coffee' not in result['context']
    assert 'review' not in result['context']
    assert result['trace'][0]['approvals']==[1,0,0]
    assert len(judge.calls)==1


def test_followup_retains_approved_evidence_and_groups_queries(products):
    agent,llm,judge,search=runner(products,
        [plan('tea'),coverage(False,['bread']),coverage(True)],[[1,0,0],[0,0,1]])
    result=agent.run('find tea and bread')
    assert result['retrieval_ok']
    assert [s['query'] for s in result['sections']]==['tea','bread']
    assert result['searches']==2
    assert 'Query: tea' in result['context'] and 'Query: bread' in result['context']
    payload=json.loads(llm.calls[-1][1]['content'])
    assert len(payload['approved_evidence'])==2


def test_filter_extraction_goes_to_existing_search_tool(products):
    p={'rewritten_query':'tea under 100','queries':[{'query':'tea','filters':{'max_price':100,'in_stock':True}}]}
    agent,_,_,search=runner(products,[p,coverage(True)],[[1,0,0]])
    agent.run('tea available under 100 USD')
    assert search.calls[0][1]['max_price']==100
    assert search.calls[0][1]['in_stock']


def test_repeated_queries_stop_without_false_success(products):
    agent,_,_,search=runner(products,[plan('tea'),coverage(False,['tea'])],[[1,0,0]])
    result=agent.run('tea and unsupported facts')
    assert not result['retrieval_ok']
    assert result['stop_reason']=='no_new_queries'
    assert len(search.calls)==1


def test_round_limit_preserves_partial_evidence(products):
    agent,_,_,_=runner(products,[plan('tea'),coverage(False,['bread'])],[[1,0,0]],retrieval_max_rounds=1)
    result=agent.run('tea and bread')
    assert result['status']=='partial'
    assert result['stop_reason']=='round_limit'


def test_search_budget_stops_followups(products):
    agent,_,_,search=runner(products,[plan('tea'),coverage(False,['bread'])],[[1,0,0]],retrieval_max_searches=1)
    result=agent.run('tea and bread')
    assert not result['retrieval_ok']
    assert result['stop_reason']=='search_limit'
    assert len(search.calls)==1


def test_initial_subqueries_are_processed_before_completion(products):
    agent,_,_,search=runner(products,
        [plan('tea','bread'),coverage(True),coverage(True)],[[1,0,0],[0,0,1]],retrieval_queries_per_round=1)
    result=agent.run('tea and bread')
    assert result['retrieval_ok']
    assert len(search.calls)==2
    assert not result['trace'][0]['retrieval_ok']


def test_completion_without_approved_chunks_is_rejected(products):
    agent,_,_,_=runner(products,[plan('tea'),coverage(True)],[[0,0,0]])
    result=agent.run('tea')
    assert not result['retrieval_ok']
    assert result['status']=='insufficient'
    assert result['context']==''


def test_wrong_chunk_label_count_fails_closed(products):
    agent,_,_,_=runner(products,[plan('tea')],[[1]])
    with pytest.raises(RuntimeError,match='count'):
        agent.run('tea')


def test_json_repair_is_bounded():
    llm=ScriptedLLM(['not JSON',plan('tea')])
    assert ask_json(llm,'rewrite',{},RetrievalPlan,retries=1).queries[0].query=='tea'
    with pytest.raises(StructuredResponseError):
        ask_json(ScriptedLLM(['invalid','invalid']),'rewrite',{},RetrievalPlan,retries=1)


def test_jev_batches_pairs_thresholds_probabilities_and_maps_ids(products):
    _,_,items=products
    def respond(request):
        body=json.loads(request.content)
        assert body['model']=='jev-1.13.0'
        assert len(body['questions'])==2
        assert body['questions']['chunk_0']['type']=='noul'
        assert request.headers['Authorization']=='Bearer test-key'
        return httpx.Response(200,json={'model':'jev-1.13.0','answers':{
            'chunk_1':{'type':'noul','noul':0.3},'chunk_0':{'type':'noul','noul':0.7}}})
    settings=Settings(_env_file=None,typesafe_api_key='test-key',retrieval_relevance_threshold=0.6)
    judge=JevClient(settings,transport=httpx.MockTransport(respond))
    result=judge.grade('tea',[{'query':'tea','filters':{},'product':p} for p in items[:2]])
    assert [d['approval'] for d in result['decisions']]==[1,0]


def test_jev_missing_answers_rejected(products):
    _,_,items=products
    transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'model':'test','answers':{}}))
    with pytest.raises(RuntimeError,match='chunk IDs'):
        JevClient(Settings(_env_file=None,typesafe_api_key='test'),transport).grade(
            'tea',[{'query':'tea','filters':{},'product':items[0]}])


def test_jev_key_required_before_network():
    with pytest.raises(RuntimeError,match='TYPESAFE_API_KEY'):
        JevClient(Settings(_env_file=None)).grade('tea',[{}])


def test_venice_uses_its_key_model_and_decisions_endpoint(products):
    _,_,items=products
    def respond(request):
        assert str(request.url)=='https://api.venice.ai/api/v1/decisions'
        assert request.headers['Authorization']=='Bearer test-venice-key'
        assert json.loads(request.content)['model']=='jev-latest'
        return httpx.Response(200,json={'model':'jev-latest','answers':{'chunk_0':{'type':'noul','noul':0.9}}})
    settings=Settings(_env_file=None,jev_provider='venice',venice_api_key='test-venice-key',jev_model='jev-latest')
    result=JevClient(settings,httpx.MockTransport(respond)).grade(
        'tea',[{'query':'tea','filters':{},'product':items[0]}])
    assert result['decisions'][0]['approval']==1


def test_venice_missing_key_does_not_fall_back_to_typesafe():
    settings=Settings(_env_file=None,jev_provider='venice',typesafe_api_key='different-key')
    with pytest.raises(RuntimeError,match='VENICE_API_KEY'):
        JevClient(settings).grade('tea',[{}])


@pytest.mark.parametrize('probability',[float('nan'),float('inf'),-0.1,1.1,True])
def test_jev_invalid_probabilities_are_rejected(products,probability):
    from pydantic import ValidationError
    _,_,items=products
    transport=httpx.MockTransport(lambda _:httpx.Response(200,json={
        'model':'test','answers':{'chunk_0':{'type':'noul','noul':probability}}}))
    with pytest.raises((ValidationError,ValueError)):
        JevClient(Settings(_env_file=None,typesafe_api_key='test'),transport).grade(
            'tea',[{'query':'tea','filters':{},'product':items[0]}])


def test_calories_reach_relevance_coverage_and_final_context(products):
    database,service,items=products
    product=service.update(items[0]['product_id'],{'calories_per_100':194,'calorie_basis':'per_100g','calorie_status':'estimated','calorie_notes':'As sold'})['product']
    agent,llm,judge,_=runner((database,service,[product]),[plan('tea calories'),coverage(True)],[[1]])
    result=agent.run('How many calories are in this tea?')
    assert judge.calls[0][0]['product']['calories_per_100']==194
    approved=json.loads(llm.calls[-1][1]['content'])['approved_evidence'][0]['products'][0]
    assert approved['calorie_basis']=='per_100g' and approved['calorie_status']=='estimated'
    assert result['sections'][0]['chunks'][0]['product']['calories_per_100']==194
    assert 'calories_per_100' in result['context']


def test_both_sources_run_and_sql_projection_reaches_customer_evidence(products):
    p = {'rewritten_query':'beverage calories','queries':[{'query':'beverage calories','source':'both',
         'filters':{'category_id':1},'catalog':{'fields':['calories_per_100'],'all_matches':True}}]}
    agent,llm,judge,search = runner(products,[p,coverage(True)],[[1,1,1,1,1]])
    result = agent.run('Get all beverage calorie information')
    assert result['retrieval_ok'] and len(search.calls) == 1 and result['searches'] == 2
    assert len(result['sections']) == 2
    sql = result['sections'][1]
    assert sql['selection']['total_matches'] == 2
    assert all(c['sources'] == ['sql'] for c in sql['chunks'])
    assert 'price' not in sql['chunks'][0]['product']
    assert 'calorie_basis' in sql['chunks'][0]['product']
    payload = json.loads(llm.calls[0][1]['content'])
    assert 'product_output_schema' in payload and 'catalog_query_schema' in payload


def test_sql_full_selection_cannot_be_complete_when_page_is_missing(products):
    p = {'rewritten_query':'all beverages','queries':[{'query':'all beverages','source':'sql',
         'filters':{'category_id':1},'catalog':{'all_matches':True,'limit':1}}]}
    agent,_,_,_ = runner(products,[p,coverage(True)],[[1]],retrieval_max_rounds=1)
    result = agent.run('All beverages')
    assert not result['retrieval_ok'] and result['status'] == 'partial'
    assert 'Full SQL selection is not yet approved' in result['missing_information']


def test_sql_followup_page_completes_full_selection(products):
    task = {'query':'all beverages','source':'sql','filters':{'category_id':1},
            'catalog':{'all_matches':True,'limit':1}}
    follow = {**task,'catalog':{**task['catalog'],'offset':1}}
    p = {'rewritten_query':'all beverages','queries':[task]}
    agent,_,_,search = runner(products,[p,{'retrieval_ok':False,'missing_information':['next page'],
                                         'followup_queries':[follow]},coverage(True)],[[1],[1]])
    result = agent.run('All beverages')
    assert result['retrieval_ok'] and result['searches'] == 2
    assert search.calls == []


def test_rejected_sql_row_prevents_whole_category_claim(products):
    p = {'rewritten_query':'all beverages','queries':[{'query':'all beverages','source':'sql',
         'filters':{'category_id':1},'catalog':{'all_matches':True}}]}
    agent,_,_,_ = runner(products,[p,coverage(True)],[[1,0]],retrieval_max_rounds=1)
    assert not agent.run('All beverages')['retrieval_ok']


def test_both_sources_cannot_claim_complete_if_budget_skips_sql(products):
    p = {'rewritten_query':'tea','queries':[{'query':'tea','source':'both'}]}
    agent,_,_,_ = runner(products,[p,coverage(True)],[[1,0,0]],retrieval_max_searches=1)
    result = agent.run('Tea information from both sources')
    assert not result['retrieval_ok']
    assert 'Initial searches could not all be executed' in result['missing_information']


def test_large_sql_result_is_graded_in_bounded_batches(products):
    p = {'rewritten_query':'all products','queries':[{'query':'all products','source':'sql',
          'catalog':{'all_matches':True}}]}
    agent,_,judge,_ = runner(products,[p,coverage(True)],[[1,1],[1]],retrieval_relevance_batch_size=2)
    assert agent.run('All product information')['retrieval_ok']
    assert [len(batch) for batch in judge.calls] == [2,1]
