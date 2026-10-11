import argparse
import json
from app.config import get_settings
from app.database.connection import migrate
from app.model_clients.factory import embedding_client, vector_index
from app.product_search.service import create_search_service
from app.agents.retrieval.agent import create_runner
from app.utils.logging import configure_logging


def main():
    parser = argparse.ArgumentParser(description="Rewrite, search, validate and combine approved product evidence")
    parser.add_argument("query")
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    migrate(settings.database_path)
    vectors = vector_index(settings)
    try:
        search = create_search_service(settings, embedding_client(settings), vectors)
        result = create_runner(settings, search).run(args.query)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    finally:
        vectors.close()


if __name__ == "__main__":
    main()
