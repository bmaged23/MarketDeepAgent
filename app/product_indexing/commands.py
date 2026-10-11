import argparse
import json
from app.config import get_settings
from app.database.connection import connection, migrate
from app.product_indexing.service import schedule_all, reconcile
from app.product_indexing.processor import IndexingProcessor
from app.model_clients.factory import embedding_client, vector_index
from app.utils.logging import configure_logging


def main():
    parser = argparse.ArgumentParser(description="Product indexing and synchronization")
    parser.add_argument("command", choices=["migrate", "index-all", "process", "watch", "reconcile", "rebuild-bm25", "status"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Retry failed jobs without waiting for backoff")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    configure_logging()
    settings = get_settings()
    migrate(settings.database_path)
    embeddings = embedding_client(settings)
    vectors = vector_index(settings)
    processor = IndexingProcessor(settings.database_path, embeddings, vectors, settings.indexing_max_retry_seconds)
    try:
        if args.command == "migrate":
            print("Database migrations applied")
        elif args.command == "index-all":
            print(json.dumps({"queued": schedule_all(settings.database_path)}))
        elif args.command == "process":
            print(json.dumps(processor.run_once(args.limit or settings.indexing_batch_size, force=args.force)))
        elif args.command == "watch":
            processor.run_forever(settings.indexing_poll_seconds, settings.indexing_batch_size)
        elif args.command == "reconcile":
            print(json.dumps({"queued": reconcile(settings.database_path, vectors)}))
        elif args.command == "rebuild-bm25":
            with connection(settings.database_path, write=True) as conn:
                conn.execute("DELETE FROM product_fts")
                conn.execute("INSERT INTO product_fts(rowid,name,category,description,nutrition) SELECT p.product_id,p.name,c.name,p.description,CASE WHEN p.calories_per_100 IS NULL THEN '' ELSE 'Calories: ' || p.calories_per_100 || ' kcal ' || replace(p.calorie_basis,'_',' ') || '. ' || p.calorie_status || '. ' || coalesce(p.calorie_notes,'') END FROM product p JOIN category c USING(category_id)")
            print("BM25 rebuilt")
        elif args.command == "status":
            with connection(settings.database_path) as conn:
                print(json.dumps([dict(r) for r in conn.execute("SELECT status,COUNT(*) AS count FROM product_index_jobs GROUP BY status")]))
    except KeyboardInterrupt:
        pass
    finally:
        vectors.close()


if __name__ == "__main__":
    main()
