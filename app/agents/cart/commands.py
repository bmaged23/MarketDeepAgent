import argparse
import json
from app.config import get_settings
from app.database.connection import migrate
from app.agents.cart.agent import create_runner
from app.agents.cart.tools import CartTools


def main():
    parser = argparse.ArgumentParser(description="Run the customer-bound cart specialist or explicitly confirm a checkout quote")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--person-id", type=int, required=True, help="Trusted local customer ID; not web authentication")
    parser.add_argument("--confirm-token")
    parser.add_argument("--confirmed", action="store_true")
    parser.add_argument("--payment-method", choices=["cash_on_delivery"])
    parser.add_argument("--delivery-address")
    args = parser.parse_args()
    settings = get_settings()
    migrate(settings.database_path)
    if args.confirm_token:
        if not args.confirmed or not args.payment_method or not args.delivery_address:
            parser.error("Confirmed checkout requires --confirmed, --payment-method and --delivery-address")
        result = CartTools(settings, args.person_id).complete_order({"token": args.confirm_token,
            "confirmed": True, "payment_method": args.payment_method, "delivery_address": args.delivery_address})
    else:
        if not args.query:
            parser.error("Supply a request or --confirm-token")
        result = create_runner(settings, args.person_id).run(args.query)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
