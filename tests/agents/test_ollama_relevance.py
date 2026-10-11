import json
import pytest
from app.config import Settings
from app.agents.retrieval.agent import RetrievalAgent, create_runner
from app.agents.retrieval.tools import RetrievalTools
from app.agents.retrieval.relevance import OllamaRelevanceJudge
from app.utils.llm_json import StructuredResponseError


class LLM:
    usage = []
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []
    def chat(self, messages):
        self.calls.append(messages)
        return {"message": {"content": json.dumps(next(self.responses))}}


def test_batch_approval_and_followup_loop(products):
    database, _, items = products
    class Search:
        def search(self, query, filters, limit):
            return {"degraded": False, "results": [{"product": p, "score": 1, "sources": ["vector"]} for p in items]}
    llm = LLM([
        {"rewritten_query": "tea and bread", "queries": [{"query": "tea"}]},
        {"approved_chunk_ids": ["chunk_0"]},
        {"retrieval_ok": False, "followup_queries": [{"query": "bread"}], "missing_information": ["bread"]},
        {"approved_chunk_ids": ["chunk_2"]},
        {"retrieval_ok": True},
    ])
    settings = Settings(_env_file=None, database_path=database)
    agent = RetrievalAgent(settings, RetrievalTools(database, Search()), llm, OllamaRelevanceJudge(settings, llm))
    result = agent.run("tea and bread")
    assert result["retrieval_ok"] and result["searches"] == 2
    assert [s["chunks"][0]["product"]["name"] for s in result["sections"]] == ["Black Tea", "Bread"]
    for i in [1, 3]:
        payload = json.loads(llm.calls[i][1]["content"])
        assert len(payload["chunks"]) == 3
    coverage = json.loads(llm.calls[4][1]["content"])
    assert len(coverage["approved_evidence"]) == 2
    assert result["trace"][0]["approvals"] == [1, 0, 0]
    assert "jev" not in result["model_usage"]


@pytest.mark.parametrize("ids", [["invented"], ["chunk_0", "chunk_0"]])
def test_invalid_approval_ids_rejected(products, ids):
    _, _, items = products
    judge = OllamaRelevanceJudge(Settings(_env_file=None, retrieval_json_retries=0), LLM([{"approved_chunk_ids": ids}]))
    with pytest.raises(StructuredResponseError):
        judge.grade("tea", [{"query": "tea", "filters": {}, "product": items[0]}])


def test_empty_approval_rejects_all_and_empty_batch_skips_model(products):
    _, _, items = products
    llm = LLM([{"approved_chunk_ids": []}])
    judge = OllamaRelevanceJudge(Settings(_env_file=None), llm)
    result = judge.grade("tea", [{"query": "tea", "filters": {}, "product": p} for p in items])
    assert [d["approval"] for d in result["decisions"]] == [0, 0, 0]
    assert judge.grade("tea", [])["decisions"] == []
    assert len(llm.calls) == 1


def test_runner_needs_only_ollama_key(products):
    database, _, _ = products
    settings = Settings(_env_file=None, database_path=database, ollama_api_key="test")
    assert isinstance(create_runner(settings, None).judge, OllamaRelevanceJudge)
