import json
from app.config import PROJECT_ROOT
from scripts.evaluation.run_suite import validate_dataset,oracle_product_checks


def test_frozen_dataset_coverage_and_independent_references():
    manifest,cases=validate_dataset()
    assert manifest['counts']=={'retrieval':30,'cart':25,'customer':25,'journey':20}
    catalog=json.loads((PROJECT_ROOT/'evaluation/datasets/catalog-v1.json').read_text())['products']
    by_id={p['product_id']:p for p in catalog}
    for case in cases:
        if case['scope']=='retrieval':
            assert case['relevant_product_ids']
            assert set(case['relevant_product_ids'])=={p['product_id'] for p in case['reference_evidence']}
            for ref in case['reference_evidence']:assert ref==by_id[ref['product_id']]
            assert case['oracle_sql']['parameters']==case['relevant_product_ids']
        if case['scope']=='journey':
            assert len(case['turns'])==6
            prices={str(p['product_id']):p['price'] for p in case['reference_evidence']}
            expected=case['reference_answer_facts']
            assert round(sum(prices[k]*v for k,v in expected['expected_final_quantities'].items()),2)==expected['expected_total']
            assert all(k in prices for t in case['turns'] for k in t['expected_cart'])


def test_oracle_detects_invented_prices_and_violated_filters():
    gold=[{'product_id':7,'name':'Apples','price':4.0,'stock_quantity':3,'category_id':2}]
    good={'product':dict(gold[0]),'approval':1}
    assert all(oracle_product_checks([good],gold,{'max_price':5,'in_stock':True}).values())
    wrong={'product':{**gold[0],'price':6.0},'approval':1}
    checked=oracle_product_checks([wrong],gold,{'max_price':5})
    assert not checked['facts_match_sql'] and not checked['constraints_satisfied']
    assert not oracle_product_checks([{**good,'approval':0}],gold,{})['approved_only']


def test_judge_accepts_exact_json_fences_but_not_missing_fields():
    import pytest
    from scripts.evaluation.judge_answers import parse_judgment,Correctness,Faithfulness
    content='```json\n{"correctness":2,"completeness":1,"relevance":3,"reason":"Partial response."}\n```'
    result=parse_judgment(Correctness,content)
    assert result.correctness==2
    with pytest.raises(ValueError):parse_judgment(Faithfulness,'{"score":4,"reason":"Unsupported field name"}')


def test_cross_field_repair_explains_only_allowlisted_static_rule():
    from app.utils.llm_json import ask_json
    from app.agents.retrieval.schemas import RetrievalPlan
    class Model:
        def __init__(self):self.messages=[]
        def chat(self,messages):
            self.messages.append(list(messages))
            if len(self.messages)==1:return {'message':{'content':json.dumps({'rewritten_query':'tea','queries':[{'query':'tea','source':'hybrid','catalog':{'name_contains':'tea'}}]})}}
            assert 'For source=hybrid omit catalog' in messages[-1]['content']
            return {'message':{'content':json.dumps({'rewritten_query':'tea','queries':[{'query':'tea','source':'hybrid'}]})}}
    assert ask_json(Model(),'Plan',{'request':'tea'},RetrievalPlan).queries[0].catalog is None


def test_release_gate_blocks_missing_coverage_nan_and_critical_failures():
    import copy
    from scripts.evaluation.check_gate import assess
    policy={'dataset_sha256':'x','dataset_version':'v','cases':1,'counts':{'journey':1},
        'minimum_scope_pass_rates':{'journey':.8},'maximum_absolute_scope_regression':.03,
        'critical_journey_checks':['idempotent_checkout'],'critical_no_false_checks':['no_unconfirmed_order'],
        'expected_answer_judgments':1,'minimum_answer_scores':{'faithfulness':.9}}
    summary={'dataset_sha256':'x','dataset_version':'v','completed':1,'image_id':'sha256:example','scopes':{'journey':{'pass_rate':1.0}}}
    rows=[{'case_id':'j','scope':'journey','passed':True,'checks':{'idempotent_checkout':True,'turn_1.no_unconfirmed_order':True}}]
    judge={'expected_answers':1,'completed_judgments':2,'valid_judgments':2,'metrics':{'faithfulness':{'mean':1.0,'scored_answers':1}}}
    assert not assess(summary,rows,judge,policy,summary)
    bad=copy.deepcopy(summary);bad['scopes']['journey']['pass_rate']=float('nan')
    assert assess(bad,rows,judge,policy,summary)
    assert assess(summary,[],judge,policy,summary)
    bad_rows=copy.deepcopy(rows);bad_rows[0]['checks']['idempotent_checkout']=False
    assert assess(summary,bad_rows,judge,policy,summary)
    bad_judge=copy.deepcopy(judge);bad_judge['valid_judgments']=1
    assert assess(summary,rows,bad_judge,policy,summary)
