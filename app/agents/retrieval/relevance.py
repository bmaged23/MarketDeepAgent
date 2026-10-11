from app.agents.retrieval.schemas import RelevanceDecision
from app.utils.llm_json import ask_json, StructuredResponseError
from app.utils.prompt_loader import load_prompt


class OllamaRelevanceJudge:
    """One batch decision for every newly retrieved query/product chunk in a round."""
    def __init__(self, settings, llm):
        self.settings, self.llm = settings, llm

    def grade(self, request, chunks):
        if not chunks:
            return {"decisions": [], "approved_chunk_ids": [], "model": self.settings.ollama_model, "usage": []}
        candidates = [{"chunk_id": f"chunk_{i}", "query": c["query"],
                       "filters": c["filters"], "product": c["product"]}
                      for i, c in enumerate(chunks)]
        before = len(getattr(self.llm, "usage", []))
        decision = ask_json(self.llm, load_prompt("retrieval", "relevance.md"),
                            {"request": request, "chunks": candidates}, RelevanceDecision,
                            self.settings.retrieval_json_retries)
        approved = set(decision.approved_chunk_ids)
        if not approved <= {c["chunk_id"] for c in candidates}:
            raise StructuredResponseError("Relevance judge returned unknown chunk IDs")
        return {"decisions": [{"approval": int(c["chunk_id"] in approved), "probability": None}
                              for c in candidates],
                "approved_chunk_ids": decision.approved_chunk_ids,
                "model": self.settings.ollama_model,
                "usage": getattr(self.llm, "usage", [])[before:]}
