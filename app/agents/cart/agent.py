from pydantic import ValidationError
from app.agents.cart.tools import CartTools
from app.agents.cart.schemas import CartDecision
from app.agents.definition import AgentDefinition
from app.agents.retrieval.schemas import RetrievalRequest
from app.utils.llm_json import ask_json
from app.utils.prompt_loader import load_prompt
from app.utils.errors import ServiceError
from app.utils.shopping_intent import explicit_shopping_intent


class CartAgent:
    def __init__(self, settings, tools, llm):
        self.settings, self.tools, self.llm = settings, tools, llm

    def run(self, query, evidence=None, history=None):
        query = RetrievalRequest(query=query).query
        cart = self.tools.view_cart()
        evidence = evidence or {}
        intent = explicit_shopping_intent(query)
        # Delivery eligibility is an owned SQL fact, not something to ask the shopper
        # to attest to. Fetch only the requested order and do not send its address.
        import re
        order_match = re.search(r"\border\s*#?\s*(\d+)\b", query, re.I)
        requested_order = None
        if order_match and re.search(r"\b(?:rate|rating|comment)\b|\b(?:submit|post|leave|write)\b.*\breview\b", query, re.I):
            try:
                order = self.tools.order_status(int(order_match.group(1)))
            except ServiceError:
                return {"status": "validation_failed", "action": "review_product",
                        "reason": "Order not found for this customer"}
            if not order["review_eligible"]:
                return {"status": "validation_failed", "action": "review_product",
                        "reason": "Reviews are allowed only after delivery"}
            requested_order = {k: order[k] for k in ("order_id", "status", "review_eligible", "items")}
        if intent in {"prepare_checkout", "order_history", "view_cart"}:
            # Current explicit read/quote operations never authorize a cart write.
            decision = CartDecision(action=intent)
        elif intent == "order_status":
            import re
            match = re.search(r"\border\s*(?:#\s*)?(\d+)\b", query, re.I)
            decision = CartDecision(action="order_status", order_id=int(match.group(1)))
        else:
            decision = ask_json(self.llm, load_prompt("cart"),
                {"request": query, "cart": cart, "catalog_evidence": evidence,
                 "requested_order": requested_order,
                 "conversation_history": history or []}, CartDecision, self.settings.cart_json_retries)
        if decision.action == "clarify":
            return {"status": "needs_clarification", "question": decision.clarification, "cart": cart}
        # Model-selected additions must resolve to supplied product evidence or existing cart IDs.
        allowed = {p["product_id"] for p in cart["items"]}
        allowed.update(c["product"]["product_id"] for section in evidence.get("sections", []) for c in section["chunks"] if c.get("approval") == 1)
        if decision.action == "update_cart" and any(i.product_id not in allowed for i in decision.items):
            return {"status": "needs_retrieval", "query": query, "reason": "Resolve requested products with retrieval first"}
        try:
            method = getattr(self.tools, decision.action)
            if decision.action == "update_cart":
                output = method([i.model_dump() for i in decision.items])
            elif decision.action == "review_product":
                output = method(decision.order_id, decision.product_id, decision.rating, decision.comment)
            elif decision.action == "order_status":
                output = method(decision.order_id)
            else:
                output = method()
            return {"status": "ok", "action": decision.action, "output": output}
        except (ServiceError, ValueError, ValidationError) as exc:
            return {"status": "validation_failed", "action": decision.action,
                    "reason": exc.detail if isinstance(exc, ServiceError) else "Invalid cart arguments"}


def create_agent(settings, person_id):
    tools = CartTools(settings, person_id)
    names = ("view_cart", "update_cart", "clear_cart", "validate_cart", "quote_cart", "prepare_checkout", "order_history", "order_status", "review_product")
    return AgentDefinition("cart", load_prompt("cart"), {name: getattr(tools, name) for name in names})


def create_runner(settings, person_id, llm=None):
    from app.model_clients.ollama import OllamaClient
    if llm is None and (settings.llm_provider != "ollama" or not settings.ollama_api_key.get_secret_value()):
        raise RuntimeError("Configure Ollama credentials for the cart agent")
    return CartAgent(settings, CartTools(settings, person_id), llm or OllamaClient(settings))
