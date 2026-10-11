class CustomerTools:
    """Delegate to specialists, sharing approved evidence in memory."""
    def __init__(self, retrieval_agent, cart_agent):
        self.retrieval_agent, self.cart_agent = retrieval_agent, cart_agent

    def retrieve_products(self, query):
        return self.retrieval_agent.run(query)

    def manage_cart(self, query, evidence=None, history=None):
        return self.cart_agent.run(query, evidence=evidence, history=history)


    def complete_confirmed_order(self, confirmation):
        """Called by trusted application code after explicit customer confirmation."""
        return self.cart_agent.tools.complete_order(confirmation)

    def application_help(self):
        """Return the allowlisted pages and supported customer operations."""
        from app.application_guide.registry import application_help
        return application_help()
