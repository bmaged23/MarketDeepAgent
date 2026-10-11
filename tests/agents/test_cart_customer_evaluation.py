import json
from app.config import Settings
from app.database.connection import connection
from app.agents.cart.evaluation import CASES as CART_CASES, evaluate_cases as cart_cases, evaluate_tools
from app.agents.customer.evaluation import CASES as CUSTOMER_CASES, evaluate_cases as customer_cases
from app.utils.agent_evaluation import evaluation_catalog, save_report, record_case


def snapshot(database):
    with connection(database) as conn:
        return {table: [tuple(r) for r in conn.execute(f"SELECT * FROM {table}")] for table in
                ("product", "person", "orders", "customer_cart", "verified_product_reviews")}


def test_all_offline_cart_cases_and_tools_leave_source_unchanged(products):
    database, _, _ = products
    settings = Settings(_env_file=None, database_path=database)
    before = snapshot(database)
    cases = cart_cases(settings, CART_CASES, offline=True)
    assert len(cases) == 12 and all(c["passed"] for c in cases)
    assert all(c["passed"] for c in evaluate_tools(settings))
    assert snapshot(database) == before


def test_all_offline_customer_cases_leave_source_unchanged(products):
    database, _, _ = products
    settings = Settings(_env_file=None, database_path=database)
    before = snapshot(database)
    cases = customer_cases(settings, CUSTOMER_CASES, offline=True)
    assert len(cases) == 10 and all(c["passed"] for c in cases)
    checkout = next(c for c in cases if c["case_id"] == "confirmed_checkout")
    assert checkout["checks"]["stock_deducted_once"]
    assert any(c.get("component") == "retrieval" and c["operation"] == "grade" for row in cases for c in row["calls"])
    assert snapshot(database) == before


def test_isolation_excludes_real_customer_data_and_cleans_up(products):
    database, _, _ = products
    with connection(database, write=True) as conn:
        conn.execute("INSERT INTO person(first_name,last_name,email,address) VALUES('Private','Customer','private@example.test','Private address')")
    settings = Settings(_env_file=None, database_path=database)
    with evaluation_catalog(settings) as (isolated, _, _):
        path = isolated.database_path
        with connection(path) as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM person")]
        assert len(rows) == 2 and "Private" not in str(rows)
    assert not path.exists()


def test_report_retains_errors_without_secret_messages(tmp_path):
    def fail(): raise RuntimeError("secret")
    row = record_case("failure", "query", fail, None, [])
    path = tmp_path / "report.json"
    assert save_report({"mode": "offline_scripted", "cases": [row]}, path) == 1
    report = json.loads(path.read_text())
    assert report["summary"]["passed_cases"] == 0
    assert report["cases"][0]["error_type"] == "RuntimeError"
    assert "secret" not in path.read_text()


def test_safe_cart_first_fallback_passes_mutation_order_check(products, monkeypatch):
    from app.agents.customer import evaluation
    from app.utils.agent_evaluation import ScriptedLLM
    class CartFirstLLM(ScriptedLLM):
        def __init__(self, replies):
            if replies and replies[0].get("steps") == ["retrieval", "cart"]:
                replies = [{"steps": ["cart"]}, *replies[1:]]
            super().__init__(replies)
    monkeypatch.setattr(evaluation, "ScriptedLLM", CartFirstLLM)
    database, _, _ = products
    case = evaluation.evaluate_cases(Settings(_env_file=None,database_path=database), ["add_products"], offline=True)[0]
    assert case["passed"]
    assert case["checks"]["retrieval_before_cart_mutation"]
    calls = [c["operation"] for c in case["calls"]]
    assert calls.index("manage_cart") < calls.index("retrieve_products") < calls.index("update_cart")


def test_customer_reply_currency_repair():
    import pytest
    from app.agents.customer.schemas import CustomerReply
    from app.utils.agent_evaluation import ScriptedLLM
    from app.utils.llm_json import ask_json
    for amount in ["32 EGP", "EGP 32", "EUR 32", "32 euros"]:
        with pytest.raises(ValueError): CustomerReply(answer=amount)
    result = ask_json(ScriptedLLM([{"answer": "Price is 32 EGP"}, {"answer": "Price is $32"}]),
                     "All amounts in USD", {}, CustomerReply, retries=1)
    assert result.answer == "Price is $32"


def test_repeated_shopping_journeys_place_two_isolated_orders_each(products):
    from app.agents.customer.journey_evaluation import evaluate_journey, OfflineEmbeddings
    from app.product_search.vector_index import QdrantProductIndex
    from qdrant_client import QdrantClient
    database,service,items=products
    for p in items:
        service.update(p['product_id'],{'calories_per_100':100,'calorie_basis':'per_100g'})
    before=snapshot(database)
    vectors=QdrantProductIndex('','journey_test',2,'test-embedding',client=QdrantClient(':memory:'))
    try:
        for p in items: vectors.upsert(p,[1,0],'test')
        for repetition in (1,2):
            rows=evaluate_journey(Settings(_env_file=None,database_path=database),repetition,True,OfflineEmbeddings(),vectors)
            assert len(rows)==19
            assert all(r['passed'] for r in rows),[(r['case_id'],r.get('checks'),r.get('error_type')) for r in rows if not r['passed']]
            confirmations=[r for r in rows if '_confirm_' in r['case_id']]
            assert len(confirmations)==2
            assert all(r['checks']['stock_deducted_once'] and r['checks']['idempotent_checkout'] for r in confirmations)
        assert snapshot(database)==before
    finally: vectors.close()


def test_evaluation_traces_structured_sql_arguments(products):
    from app.utils.evaluation_trace import RecordedClient
    from app.agents.retrieval.tools import RetrievalTools
    from app.products.catalog_query import CatalogQuery
    database,_,_=products
    records=[]
    tool=RecordedClient(RetrievalTools(database,None),records,{'query_products'})
    tool.query_products(CatalogQuery(fields=['price']),{'category_id':1})
    assert records[0]['input']['args'][0]['fields']==['price']
    assert records[0]['status']=='ok'
