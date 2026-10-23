"""Recognize explicit English operations to constrain stale model routing.

Ambiguous requests remain LLM decisions. These rules never authorize checkout confirmation.
"""
import re


def explicit_shopping_intent(query):
    text = query.strip().casefold()
    # Preparing a quote remains explicit when the later clause forbids placement.
    # This never authorizes confirmation or turns a negated checkout into an action.
    if re.match(r'^(?:(?:can|could|would) you\s+)?(?:please\s+)?(?:prepare|start|begin)\s+(?:the\s+)?(?:checkout|check out)\b', text):
        first_clause = re.split(r'[,;]|\bbut\b', text, maxsplit=1)[0]
        if not re.search(r"\b(?:don't|do not|never|cancel|how|what|if|maybe)\b", first_clause):
            return 'prepare_checkout'
    # Do not turn a negative or hypothetical request into a tool operation.
    if re.search(r"\b(?:don't|do not|never|cancel)\b", text):
        return None
    if re.search(r'\b(?:checkout|check out)\b', text) and not re.search(r'\b(?:what|how|means?|explain)\b', text):
        return 'prepare_checkout'
    if re.search(r'\border\s*(?:#\s*)?\d+\b', text) and re.search(r'\b(?:status|shipping|payment|pending)\b', text):
        return 'order_status'
    if re.search(r'^(?:take me|go|navigate|open)\b.*\borders\b', text):
        return None
    if re.search(r'\borders\b', text) and re.search(r'\b(?:my|previous|past|pending|history)\b', text):
        return 'order_history'
    if re.search(r'\badd\b.*\bcart\b', text) and not re.search(r'\b(?:how|explain)\b', text):
        return 'update_cart'
    if re.search(r'\b(?:show|view|open|check)\b.*\b(?:my|the) cart\b', text):
        return 'view_cart'
    if re.search(r'^(?:(?:can|could|would|will) you\s+)?(?:okay\s+)?(?:please\s+)?(?:show|open|view)\b', text):
        if not re.search(r'\b(?:calories?|nutrition(?:al)?|average|avg|price|information|details|options|choices|compare|settings|profile|orders|cart)\b|let me choose', text):
            return 'view_product'
    return None
