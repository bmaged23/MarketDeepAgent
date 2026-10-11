"""Distinct specialists and customer coordinator, bound to a trusted customer ID."""
from app.agents.retrieval.agent import create_agent as retrieval
from app.agents.cart.agent import create_agent as cart
from app.agents.customer.agent import create_agent as customer


def create_agents(settings, search_service, person_id):
    return {"retrieval": retrieval(settings.database_path, search_service),
            "cart": cart(settings, person_id),
            "customer": customer(settings, search_service, person_id)}
