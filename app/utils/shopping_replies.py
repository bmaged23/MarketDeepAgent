"""Customer-facing factual replies derived from actual tool results."""
from app.utils.money import format_money
from app.utils.nutrition import nutrition_summary


def cart_receipt(snapshot, updated=False, max_items=10):
    items = snapshot.get('items', [])
    if not items:
        return 'Your cart was updated and is now empty.' if updated else 'Your cart is empty.'
    prefix = 'Your cart was updated. It now contains' if updated else 'Your cart contains'
    lines = '; '.join(f"{item['name']} × {item['quantity']}" for item in items[:max_items])
    more = f"; and {len(items)-max_items} more items" if len(items)>max_items else ''
    return f"{prefix} {lines}{more}. Total: {format_money(snapshot['total'])}."


def pending_order_reply(orders):
    pending = [order for order in orders if order.get('status') == 'pending']
    if not pending:
        return None
    ids = ', '.join(f"#{order['order_id']}" for order in pending)
    text = f"Order{'s' if len(pending)>1 else ''} {ids} {'are' if len(pending)>1 else 'is'} pending: placed and waiting to be processed and shipped."
    if any(order.get('payment_method') == 'cash_on_delivery' for order in pending):
        text += ' Cash on delivery is paid when the order arrives; unpaid payment status does not prevent fulfillment.'
    return text


def full_calorie_reply(retrieval):
    """Only complete, approved, explicitly exhaustive SQL selections qualify."""
    if not retrieval.get('retrieval_ok'):
        return None
    sections = [s for s in retrieval.get('sections', []) if (s.get('selection') or {}).get('all_matches')]
    products = {c['product']['product_id']:c['product'] for section in sections
                for c in section.get('chunks', []) if c.get('approval') == 1 and c.get('product')}
    if not products:
        return None
    lines = [f"- **{product['name']}** — {nutrition_summary(product) or 'Calorie information is unavailable.'}"
             for product in products.values()]
    return f"Calorie information for all {len(products)} matching products:\n\n" + '\n'.join(lines)


def remove_visible_cart_offer(answer, page):
    """Remove redundant navigation offers while preserving the rest of the reply."""
    if page != 'cart':
        return answer
    import re
    offer = re.compile(
        r"\b(?:would you like(?: me)? to|do you want(?: me)? to|shall i|can i|you can(?: also)?)"
        r"\s+(?:show(?: you)?|open|view|see|check)\s+(?:your|the)(?: shopping)? cart[^.!?\n]*[.!?]?",
        re.I,
    )
    cleaned = offer.sub('', answer).strip()
    return cleaned or 'Your cart is already open.'
