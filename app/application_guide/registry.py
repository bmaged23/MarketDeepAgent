PAGES = [
    {"id": "shop", "title": "Shop", "description": "Browse categories, search groceries and open product details."},
    {"id": "product", "title": "Product details", "description": "View the selected product's live description, USD price and stock."},
    {"id": "cart", "title": "Shopping cart", "description": "Change quantities and prepare explicitly confirmed checkout."},
    {"id": "orders", "title": "My orders", "description": "Owned order history, recorded shipping/payment status and delivered-purchase feedback."},
    {"id": "profile", "title": "My profile", "description": "Edit your name, phone and default delivery address."},
    {"id": "settings", "title": "Assistant settings", "description": "Enable or disable remembering, manage personal memories and clear conversations."},
]


def application_help():
    return {"pages": PAGES, "currency": "USD", "checkout": "Quote first; explicit confirmation, address and cash_on_delivery place an unpaid order.",
            "shipping": "Recorded order status only; carrier tracking is not connected.",
            "reviews": "Rate/comment on a purchased product only after its owned order is delivered.",
            "memory": "Remembering can be disabled. Memories can be edited/deleted in Settings. Orders/prices always come from current SQL."}
