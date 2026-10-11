import json
import re
import httpx
from app.utils.money import format_money
from app.utils.shopping_intent import explicit_shopping_intent
from app.utils.shopping_replies import cart_receipt, pending_order_reply, full_calorie_reply
from app.agents.customer.schemas import CustomerPlan, CustomerReply
from app.agents.customer.tools import CustomerTools
from app.agents.retrieval.schemas import RetrievalRequest
from app.utils.llm_json import ask_json, StructuredResponseError
from app.utils.prompt_loader import load_prompt


class CustomerAgent:
    def __init__(self, settings, tools, llm):
        self.settings, self.tools, self.llm = settings, tools, llm

    def run(self, query, history=None, context=None):
        query = RetrievalRequest(query=query).query
        context = context or {}
        intent = explicit_shopping_intent(query)
        try:
            plan = ask_json(self.llm, load_prompt("customer"), {"request": query, "history": history or [], "context": context},
                            CustomerPlan, self.settings.customer_json_retries)
        except StructuredResponseError:
            if intent not in {"prepare_checkout", "order_history", "order_status", "view_cart"}:
                raise
            # Explicit read/quote requests remain executable even if the planner
            # returns malformed JSON. No mutation or checkout confirmation is inferred.
            plan = CustomerPlan()

        if intent in {"prepare_checkout", "order_history", "order_status", "view_cart"}:
            # These requests need current customer-scoped SQL, not product search.
            plan = plan.model_copy(update={"steps": ["cart"], "specialist_query": query,
                "interaction": "checkout" if intent == "prepare_checkout" else "view_cart" if intent == "view_cart" else "answer",
                "actions": []})
        elif intent == "update_cart":
            plan = plan.model_copy(update={"interaction": "view_cart" if plan.interaction == "view_cart" else "add_to_cart",
                "steps": list(dict.fromkeys([*plan.steps, "cart"])), "specialist_query": query})
        elif intent == "view_product":
            plan = plan.model_copy(update={"interaction": "view_product", "steps": [s for s in plan.steps if s != "cart"], "specialist_query": query})
        specialist_query = plan.specialist_query or query
        steps = list(dict.fromkeys(plan.steps))
        if plan.interaction == "add_to_cart" and "cart" not in steps:
            steps.append("cart")
        if "retrieval" in steps and "cart" in steps:
            steps = ["retrieval", "cart"]
        planned_actions = self.interaction_actions(plan, plan.actions, {}, context)
        # Searching changes the shop, but does not identify product choices. Retrieve
        # actual matches before answering or resolving a subsequent "show it".
        if not steps and any(a.action == "apply_search" for a in planned_actions):
            steps = ["retrieval"]
        if plan.interaction == "view_product" and not steps and not any(a.action == "open_product" for a in planned_actions):
            steps = ["retrieval"]
        if not steps and planned_actions and all(a.trigger == "automatic" for a in planned_actions):
            # UI-only requests do not require retrieval/cart or a second answer model call.
            allowed_products = {p["product_id"]: p for p in [*context.get("referenced_products", []), *context.get("visible_products", [])]}
            selected = context.get("selected_product")
            if selected:
                allowed_products[selected["product_id"]] = selected
            actions = [a for a in planned_actions if a.action != "open_product" or a.product_id in allowed_products]
            if actions:
                descriptions = []
                for action in actions:
                    if action.action == "open_product":
                        descriptions.append(allowed_products[action.product_id]["name"] + " is already open." if selected and selected["product_id"] == action.product_id else "Opening " + allowed_products[action.product_id]["name"] + ".")
                    elif action.action == "navigate":
                        descriptions.append("Your " + action.page + " page is already open." if context.get("page_context", {}).get("page") == action.page else "Opening " + action.page.replace("_", " ") + ".")
                    elif action.action == "apply_search":
                        descriptions.append("Showing matching products in the shop.")
                    else:
                        descriptions.append("Refreshing your cart.")
                return {"answer": " ".join(descriptions), "results": {},
                        "actions": [a.model_dump() for a in actions], "memory_proposals": [],
                        "conversation_summary": context.get("conversation_summary", "")}
            # A guessed product ID must not be opened; resolve it via the retrieval specialist.
            steps = ["retrieval"]
        # Context products were reread from SQL by the authenticated API. Pass them
        # to the specialist too, so "add it" resolves the product already on screen.
        known = {p["product_id"]: p for p in context.get("referenced_products", [])}
        selected = context.get("selected_product")
        if selected:
            known[selected["product_id"]] = selected
        evidence = {"sections": [{"query": query, "chunks": [
            {"approval": 1, "product": p} for p in known.values()]}]} if known else None
        results = {}
        for step in steps:
            if step == "retrieval":
                evidence = self.tools.retrieve_products(specialist_query)
                results[step] = evidence
            else:
                results[step] = self.tools.manage_cart(specialist_query, evidence=evidence, history=history)
                if results[step].get("status") == "needs_retrieval" and evidence is None:
                    evidence = self.tools.retrieve_products(specialist_query)
                    results["retrieval"] = evidence
                    results[step] = self.tools.manage_cart(specialist_query, evidence=evidence, history=history)
        # Keep checkout authorization tokens outside customer-facing LLM context.
        payload = json.loads(json.dumps(results))
        if "retrieval" in payload:
            source = payload["retrieval"]
            payload["retrieval"] = {k: source[k] for k in ("query", "status", "retrieval_ok", "missing_information", "degraded") if k in source}
            payload["retrieval"]["sections"] = [{"query": s["query"], "selection": s.get("selection"), "products": [c["product"] for c in s["chunks"] if c.get("approval") == 1]} for s in source.get("sections", [])]
        output = payload.get("cart", {}).get("output", {})
        if isinstance(output, dict):
            output.pop("confirmation_token", None)
        reply_recovered = False
        current_cart = results.get("cart", {})
        if intent == "view_cart" and current_cart.get("status") == "ok":
            from app.application_guide.schemas import UIAction
            snapshot = current_cart["output"]
            answer = cart_receipt(snapshot, max_items=self.settings.customer_receipt_max_items)
            reply = CustomerReply(answer=answer, actions=[UIAction(action="navigate", page="cart")],
                                  conversation_summary=context.get("conversation_summary", ""))
        else:
            reply = None
        try:
            if reply is None:
                reply = ask_json(self.llm, load_prompt("customer", "answer.md"),
                                 {"request": query, "history": history or [], "specialist_results": payload, "planned_actions": [a.model_dump() for a in planned_actions], "currency": self.settings.currency, "context": context},
                                 CustomerReply, self.settings.customer_json_retries)
        except (httpx.HTTPError, StructuredResponseError):
            cart_result = results.get("cart", {})
            if cart_result.get("status") != "ok" or cart_result.get("action") not in {"update_cart", "clear_cart"}:
                raise
            # The write already committed. Return its actual receipt instead of
            # asking the customer to retry an addition that could double quantity.
            snapshot = cart_result["output"]
            answer = cart_receipt(snapshot, updated=True, max_items=self.settings.customer_receipt_max_items)
            reply = CustomerReply(answer=answer, conversation_summary=context.get("conversation_summary", ""))
            reply_recovered = True
        answer = reply.answer
        cart_result = results.get("cart", {})
        if cart_result.get("status") == "needs_clarification":
            answer = cart_result.get("question") or "Which product and quantity would you like?"
        elif cart_result.get("status") in {"validation_failed", "needs_retrieval"}:
            answer = "Your cart was not updated. " + cart_result.get("reason", "Please specify the product and quantity.")
        elif plan.interaction == "add_to_cart":
            if cart_result.get("status") == "ok" and cart_result.get("action") == "update_cart":
                items = cart_result.get("output", {}).get("items", [])
                if not items:
                    answer = "Your cart is empty; no product was added."
            else:
                answer = "No product was added to your cart. Please specify the product and quantity."
        if cart_result.get("status") == "ok":
            action = cart_result.get("action")
            if action in {"update_cart", "clear_cart"} and not re.search(r"\b(?:recommend|suggest|compare|explain|tell|calories?|nutrition|what|which|why)\b", query, re.I):
                answer = cart_receipt(cart_result["output"], updated=True,
                                      max_items=self.settings.customer_receipt_max_items)
            elif action in {"order_history", "order_status"} and re.search(r"\bpending\b", query, re.I):
                orders = cart_result["output"] if action == "order_history" else [cart_result["output"]]
                answer = pending_order_reply(orders) or answer
        if re.search(r"\ball\b", query, re.I) and re.search(r"\bcalories?\b", query, re.I) and not re.search(r"\b(?:avg|average|mean)\b", query, re.I):
            answer = full_calorie_reply(results.get("retrieval", {})) or answer
        # Treat the model's prose as untrusted: navigation/history cannot prove a write.
        claims_addition = re.search(r"\b(?:added|placed|put)\b[^.!?\n]{0,200}\b(?:your|the) cart\b", answer, re.I)
        if claims_addition and not (cart_result.get("status") == "ok" and
                                    cart_result.get("action") == "update_cart" and
                                    cart_result.get("output", {}).get("items")):
            answer = "No product was added to your cart. Please specify the product and quantity."
        card_ids = list(dict.fromkeys(reply.product_ids))
        if plan.interaction == "view_product" and not results.get("retrieval") and not card_ids:
            choices = context.get("visible_products", []) if context.get("page_context", {}).get("search") else context.get("referenced_products", [])
            if len(choices) > 1:
                card_ids = [p["product_id"] for p in choices[:10]]
        actions = self.interaction_actions(plan, reply.actions, results, context)
        if plan.interaction == "view_product":
            from app.application_guide.schemas import UIAction
            products = {c["product"]["product_id"]: c["product"]
                        for section in results.get("retrieval", {}).get("sections", [])
                        for c in section.get("chunks", []) if c.get("approval") == 1 and c.get("product")}
            if len(products) == 1:
                product = next(iter(products.values()))
                actions = [UIAction(action="open_product", product_id=product["product_id"], trigger="automatic")]
                answer = product["name"] + " is already open." if (context.get("selected_product") or {}).get("product_id") == product["product_id"] else "Opening " + product["name"] + "."
            elif len(products) > 1:
                actions = [a for a in actions if a.action not in {"open_product", "apply_search"}]
                answer = "Which product would you like to view? " + "; ".join(p["name"] for p in products.values()) + "."
        return {"answer": answer, "results": results,
                "actions": [a.model_dump() for a in actions],
                "reply_recovered": reply_recovered,
                "product_ids": card_ids,
                "memory_proposals": [m.model_dump() for m in reply.memories],
                "conversation_summary": reply.conversation_summary}

    @staticmethod
    def interaction_actions(plan, actions, results, context=None):
        """Keep suggestions optional and successful cart updates on the current page."""
        context = context or {}
        current_page = context.get("page_context", {}).get("page")
        selected_id = (context.get("selected_product") or {}).get("product_id")
        cart = results.get("cart", {})
        changed_cart = cart.get("status") == "ok" and cart.get("action") in {"update_cart", "clear_cart"}
        normalized = []
        for action in actions:
            if action.action == "refresh_cart":
                continue  # Browser synchronizes its SQL cart after every successful reply.
            trigger = action.trigger
            if action.action == "navigate" and action.page == "cart":
                if plan.interaction == "view_cart":
                    trigger = "automatic"
                elif changed_cart or plan.interaction == "add_to_cart":
                    trigger = "on_click"
            elif action.action in {"open_product", "apply_search"}:
                if plan.interaction == "view_product":
                    trigger = "automatic"
                elif "interaction" in plan.model_fields_set and plan.interaction in {"answer", "add_to_cart"}:
                    trigger = "on_click"
            if trigger == "on_click" and ((action.action == "navigate" and action.page == current_page) or (action.action == "open_product" and action.product_id == selected_id)):
                continue
            normalized.append(action.model_copy(update={"trigger": trigger}))
        if changed_cart and current_page != "cart" and not any(a.action == "navigate" and a.page == "cart" for a in normalized):
            from app.application_guide.schemas import UIAction
            normalized = normalized[:2]
            normalized.append(UIAction(action="navigate", page="cart", trigger="automatic" if plan.interaction == "view_cart" else "on_click"))
        return normalized

    def confirm_order(self, confirmation):
        """Explicit caller confirmation, never a model-generated routing decision."""
        receipt = self.tools.complete_confirmed_order(confirmation)
        order = receipt["order"]
        payment = "Payment is due on delivery" if order["payment_status"] == "unpaid" else f"Payment status: {order['payment_status']}"
        return {"answer": f"Order {order['order_id']} is placed for {format_money(order['total_amount'])}. {payment}; shipping status: {order['shipping_status']}.",
                "results": {"cart": {"action": "complete_order", "output": receipt}}}


def create_runner(settings, search_service, person_id):
    from app.agents.retrieval.agent import create_runner as retrieval
    from app.agents.cart.agent import create_runner as cart
    from app.model_clients.ollama import OllamaClient
    return CustomerAgent(settings, CustomerTools(retrieval(settings, search_service), cart(settings, person_id)), OllamaClient(settings))


def create_agent(settings, search_service, person_id):
    from app.agents.definition import AgentDefinition
    runner = create_runner(settings, search_service, person_id)
    return AgentDefinition("customer", load_prompt("customer"),
                           {"retrieve_products": runner.tools.retrieve_products,
                            "manage_cart": runner.tools.manage_cart,
                            "application_help": runner.tools.application_help})
