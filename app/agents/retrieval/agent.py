from app.products.catalog_query import CatalogQuery, ProductEvidence, project_product
from app.agents.definition import AgentDefinition
from app.agents.retrieval.tools import RetrievalTools
from app.utils.prompt_loader import load_prompt
from app.utils.llm_json import ask_json
from app.agents.retrieval.schemas import RetrievalRequest, RetrievalPlan, CoverageDecision
from app.utils.text import normalize_text
import json


def create_agent(database_path, search_service):
    tools = RetrievalTools(database_path, search_service)
    return AgentDefinition(
        "retrieval", load_prompt("retrieval"),
        {"search_products": tools.search_products,
         "product_details": tools.product_details,
         "query_products": tools.query_products,
         "compare_products": tools.compare_products},
    )


class RetrievalAgent:
    """Bounded rewrite/search/relevance/coverage loop; output is catalog evidence."""

    def __init__(self, settings, tools, llm, judge):
        self.settings, self.tools, self.llm, self.judge = settings, tools, llm, judge

    @staticmethod
    def _key(task):
        return normalize_text(task.query).casefold(), json.dumps(task.model_dump(exclude={"query"}), sort_keys=True)

    @staticmethod
    def _expand(tasks):
        expanded = []
        for task in tasks:
            if task.source == "both":
                expanded.extend([task.model_copy(update={"source": "hybrid", "catalog": None}),
                                 task.model_copy(update={"source": "sql", "catalog": task.catalog or CatalogQuery()})])
            else:
                expanded.append(task)
        return expanded

    @staticmethod
    def _evidence(sections):
        return [{"query": section["query"], "filters": section["filters"],
                 "selection": section.get("selection"),
                 "products": [chunk["product"] for chunk in section["chunks"] if chunk["approval"] == 1]}
                for section in sections if any(chunk["approval"] == 1 for chunk in section["chunks"])]

    def run(self, query):
        query = RetrievalRequest(query=query).query
        settings = self.settings
        plan = ask_json(self.llm, load_prompt("retrieval", "rewrite.md"),
                        {"request": query, "categories": self.tools.categories(),
                         "max_queries": settings.retrieval_max_searches,
                         "catalog_query_schema": CatalogQuery.model_json_schema(),
                         "product_output_schema": ProductEvidence.model_json_schema(),
                         "sql_max_results": settings.retrieval_sql_max_results}, RetrievalPlan,
                        settings.retrieval_json_retries)
        initial_tasks = self._expand(plan.queries)
        pending, visited, sections, trace = list(initial_tasks), set(), [], []
        complete, missing, stop_reason = False, [], "round_limit"
        for round_number in range(1, settings.retrieval_max_rounds + 1):
            batch, remaining = [], []
            batch_keys = set()
            for task in pending:
                key = self._key(task)
                if key in visited or key in batch_keys:
                    continue
                batch_keys.add(key)
                if len(batch) < settings.retrieval_queries_per_round:
                    batch.append(task)
                else:
                    remaining.append(task)
            pending = remaining
            if not batch:
                stop_reason = "no_new_queries"
                break
            chunks, searches = [], []
            for task in batch:
                if len(visited) >= settings.retrieval_max_searches:
                    stop_reason = "search_limit"
                    break
                visited.add(self._key(task))
                filters = task.filters.model_dump()
                if task.source == "sql":
                    result = self.tools.query_products(task.catalog, filters, settings.retrieval_sql_max_results)
                else:
                    result = self.tools.search_products(task.query, **filters,
                                                       limit=settings.retrieval_results_per_query)
                executed_task = task.model_copy(update={"catalog": task.catalog or CatalogQuery()}) if task.source == "sql" else task
                section = {"query": task.query, "filters": filters, "chunks": [],
                           "task": executed_task.model_dump(), "selection": result.get("selection")}
                seen_products = set()
                for row in result["results"]:
                    # Exclude synthetic ratings/reviews and internal indexing metadata.
                    product = project_product(row["product"], tuple(row["product"]))
                    if product["product_id"] in seen_products:
                        continue
                    seen_products.add(product["product_id"])
                    chunk = {"query": task.query, "filters": filters, "product": product,
                             "score": row["score"], "sources": row["sources"],
                             "approval": 0, "probability": None}
                    section["chunks"].append(chunk)
                    chunks.append(chunk)
                sections.append(section)
                searches.append({"query": task.query, "filters": filters,
                                 "degraded": result["degraded"], "candidates": len(section["chunks"]),
                                 "selection": result.get("selection")})
            if not searches:
                break
            grading = {"decisions": [], "usage": [], "model": settings.ollama_model}
            for offset in range(0, max(1, len(chunks)), settings.retrieval_relevance_batch_size):
                part = self.judge.grade(query, chunks[offset:offset + settings.retrieval_relevance_batch_size])
                if len(part["decisions"]) != len(chunks[offset:offset + settings.retrieval_relevance_batch_size]):
                    raise RuntimeError("Relevance decisions must match the retrieved chunk count")
                grading["decisions"].extend(part["decisions"])
                grading["usage"].append(part.get("usage", {}))
                grading["model"] = part["model"]
            if len(grading["decisions"]) != len(chunks):
                raise RuntimeError("Relevance decisions must match the retrieved chunk count")
            for chunk, decision in zip(chunks, grading["decisions"]):
                if type(decision["approval"]) is not int or decision["approval"] not in (0, 1):
                    raise RuntimeError("Relevance approval must be integer 0 or 1")
                chunk.update(decision)
            evidence = self._evidence(sections)
            coverage = ask_json(self.llm, load_prompt("retrieval", "coverage.md"),
                {"request": query, "rewritten_query": plan.rewritten_query,
                 "initial_queries": [task.model_dump() for task in plan.queries],
                 "approved_evidence": evidence,
                 "search_history": [{"task": section["task"], "selection": section["selection"],
                                     "approved_count": sum(c["approval"] for c in section["chunks"])} for section in sections],
                 "remaining_searches": max(0, settings.retrieval_max_searches - len(visited)),
                 "pending_queries": [task.model_dump() for task in pending]},
                CoverageDecision, settings.retrieval_json_retries)
            missing = coverage.missing_information
            complete = coverage.retrieval_ok and bool(evidence) and not pending
            if any(self._key(task) not in visited for task in initial_tasks):
                complete = False
                missing = [*missing, "Initial searches could not all be executed"]
            # Whole-selection claims require all SQL matches to survive approval,
            # including pages fetched in subsequent rounds.
            for section in sections:
                selection = section.get("selection")
                if not selection or not selection["all_matches"]:
                    continue
                identity = {**section["task"], "catalog": {**section["task"]["catalog"], "offset": 0, "limit": 0}}
                matching = [s for s in sections if s.get("selection") and
                            {**s["task"], "catalog": {**s["task"]["catalog"], "offset": 0, "limit": 0}} == identity]
                approved_ids = {c["product"]["product_id"] for s in matching for c in s["chunks"] if c["approval"] == 1}
                if len(approved_ids) != selection["total_matches"]:
                    complete = False
                    if "Full SQL selection is not yet approved" not in missing:
                        missing = [*missing, "Full SQL selection is not yet approved"]
            trace.append({"round": round_number, "searches": searches,
                          "approvals": [d["approval"] for d in grading["decisions"]],
                          "judge_model": grading["model"], "judge_usage": grading.get("usage", {}),
                          "validation": coverage.model_dump(), "retrieval_ok": complete})
            if complete:
                stop_reason = "complete"
                break
            pending.extend(self._expand(coverage.followup_queries))
            if len(visited) >= settings.retrieval_max_searches:
                stop_reason = "search_limit"
                break
        approved = [{**section, "chunks": [chunk for chunk in section["chunks"] if chunk["approval"] == 1]}
                    for section in sections if any(chunk["approval"] == 1 for chunk in section["chunks"])]
        if not complete and not approved and not missing:
            missing = ["No approved catalog evidence was retrieved"]
        # Build downstream context from original SQL chunks, never LLM-authored facts.
        context = "\n\n".join("Query: " + section["query"] + "\n" + "\n".join(
            json.dumps(chunk["product"], ensure_ascii=False, separators=(",", ":"))
            for chunk in section["chunks"]) for section in approved)
        return {"query": query, "rewritten_query": plan.rewritten_query,
                "status": "done" if complete else "partial" if approved else "insufficient",
                "retrieval_ok": complete, "stop_reason": stop_reason,
                "missing_information": missing,
                "sections": approved, "context": context, "trace": trace,
                "model_usage": {"ollama": getattr(self.llm, "usage", []),
                                "relevance_judge": [step["judge_usage"] for step in trace]},
                "searches": len(visited),
                "degraded": any(search["degraded"] for step in trace for search in step["searches"])}


def create_runner(settings, search_service):
    from app.model_clients.ollama import OllamaClient
    from app.agents.retrieval.relevance import OllamaRelevanceJudge
    if settings.llm_provider != "ollama":
        raise RuntimeError("Retrieval planning currently requires LLM_PROVIDER=ollama")
    if not settings.ollama_api_key.get_secret_value():
        raise RuntimeError("Set OLLAMA_API_KEY in .env")
    llm = OllamaClient(settings)
    return RetrievalAgent(settings, RetrievalTools(settings.database_path, search_service),
                          llm, OllamaRelevanceJudge(settings, llm))
