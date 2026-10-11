from types import SimpleNamespace
import pytest
from app.agents.retrieval.evaluation import RecordedClient, evaluate_tools, evaluate_agent
from app.agents.retrieval.tools import RetrievalTools
from app.database.connection import connection
from app.products.queries import list_products


def test_tool_contracts_and_inputs(products):
    database, _, _ = products
    with connection(database) as conn:
        rows = list_products(conn)
    class Search:
        def search(self, query, filters, limit):
            return {"degraded": False, "results": [{"product": rows[0], "score": .8, "sources": ["vector"]}]}
    report = evaluate_tools(RetrievalTools(database, Search()), rows, {"query": "tea"}, 5)
    assert report["passed"]
    assert len(report["checks"]) == 7
    call = next(c for c in report["calls"] if c["operation"] == "search_products")
    assert call["input"]["args"] == ["tea"]
    assert call["input"]["kwargs"] == {"limit": 5}
    assert call["output"]["results"][0]["product"] == rows[0]


def test_trace_omits_reasoning_and_error_messages():
    class Client:
        def chat(self, messages):
            return {"message": {"content": "{}", "thinking": "private reasoning"}}
        def grade(self, *args):
            raise RuntimeError("secret credential in URL")
    records = []
    proxy = RecordedClient(Client(), records, {"chat", "grade"})
    messages = [{"role": "user", "content": "tea"}]
    proxy.chat(messages)
    messages.append({"role": "user", "content": "repair"})
    assert len(records[0]["input"]["args"][0]) == 1
    assert records[0]["output"] == {"content": "{}"}
    with pytest.raises(RuntimeError):
        proxy.grade("tea", [])
    assert records[1]["error_type"] == "RuntimeError"
    assert "secret" not in str(records)


def test_agent_failure_does_not_stop_other_cases():
    def broken():
        raise RuntimeError("secret")
    cases = [{"case_id": str(i), "query": "tea", "relevant_product_names": ["Tea"]} for i in range(2)]
    reports = evaluate_agent(broken, cases, [])
    assert len(reports) == 2
    assert all(not r["passed"] and r["error_type"] == "RuntimeError" for r in reports)


def test_agent_detects_invented_facts_and_missing_expected_product(products):
    _, _, items = products
    product = {**items[0], "price": 9999}
    class Runner:
        tools = llm = judge = SimpleNamespace()
        settings = SimpleNamespace(retrieval_max_searches=8)
        def run(self, query):
            return {"sections": [{"query": "tea", "chunks": [{"product": product, "approval": 1}]}],
                    "context": "Query: tea", "retrieval_ok": True, "degraded": False, "searches": 1}
    result = evaluate_agent(Runner, [{"case_id": "x", "query": "coffee", "relevant_product_names": ["Coffee"]}], items)[0]
    assert not result["passed"]
    assert not result["checks"]["facts_match_sql"]
    assert not result["checks"]["expected_products_found"]


def test_http_failure_records_status_without_secret_response():
    import httpx
    class Client:
        def grade(self):
            request = httpx.Request("POST", "https://example.com/api/v1/decisions", headers={"Authorization": "Bearer secret"})
            response = httpx.Response(422, request=request, json={"detail": [{"loc": ["body", "questions"], "type": "string_type", "input": "secret"}]})
            response.raise_for_status()
    records = []
    with pytest.raises(httpx.HTTPStatusError):
        RecordedClient(Client(), records, {"grade"}).grade()
    assert records[0]["http_status"] == 422
    assert records[0]["validation_errors"][0]["location"] == ["body", "questions"]
    assert "secret" not in str(records)
