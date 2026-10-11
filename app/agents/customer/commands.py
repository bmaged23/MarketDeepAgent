import argparse
import json
from app.config import get_settings
from app.database.connection import migrate
from app.model_clients.factory import embedding_client, vector_index
from app.product_search.service import create_search_service
from app.agents.customer.agent import create_runner


def main():
    parser = argparse.ArgumentParser(description="Customer conversation coordinator with retrieval and cart specialists")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--person-id", type=int, required=True)
    parser.add_argument("--interactive", action="store_true", help="Keep conversation history in memory; /quit exits")
    args = parser.parse_args()
    if not args.query and not args.interactive:
        parser.error("Supply a request or --interactive")
    settings = get_settings()
    migrate(settings.database_path)
    vectors = vector_index(settings)
    try:
        search = create_search_service(settings, embedding_client(settings), vectors)
        runner = create_runner(settings, search, args.person_id)
        history = []
        query = args.query
        checkout_token = None
        while True:
            if query is None:
                try:
                    query = input("You: ")
                except (EOFError, KeyboardInterrupt):
                    break
            if query.strip() == "/quit":
                break
            if not query.strip():
                query = None
                continue
            if query.strip() == "/confirm":
                if not checkout_token:
                    print("Prepare checkout first by asking to checkout your cart.")
                    query = None
                    continue
                address = input("Delivery address: ").strip()
                payment_method = input("Payment method (cash_on_delivery): ").strip()
                confirmed = input("Place the quoted order? Type yes to confirm: ").strip().lower() == "yes"
                if not confirmed:
                    print("Checkout was not confirmed.")
                    query = None
                    continue
                try:
                    result = runner.confirm_order({"token": checkout_token, "confirmed": True,
                                                   "payment_method": payment_method, "delivery_address": address})
                    checkout_token = None
                except Exception as exc:
                    from app.utils.errors import ServiceError
                    print(exc.detail if isinstance(exc, ServiceError) else "Checkout failed; check your details and prepare checkout again.")
                    query = None
                    continue
            else:
                result = runner.run(query, history=history)
                output = result.get("results", {}).get("cart", {}).get("output", {})
                if isinstance(output, dict) and output.get("confirmation_token"):
                    checkout_token = output["confirmation_token"]
                    print("Review the quote, then use /confirm to provide checkout details.")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            history.extend([{"role": "user", "content": query}, {"role": "assistant", "content": result["answer"]}])
            history = history[-settings.customer_history_messages:]
            if not args.interactive:
                break
            query = None
    finally:
        vectors.close()


if __name__ == "__main__":
    main()
