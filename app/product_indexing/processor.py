import logging
import time
from app.database.connection import connection
from app.products.queries import get_product
from app.product_indexing.service import product_document, document_hash

logger = logging.getLogger(__name__)


class IndexingProcessor:
    def __init__(self, database_path, embeddings, vectors, max_retry_seconds=300):
        self.database_path, self.embeddings, self.vectors = database_path, embeddings, vectors
        self.max_retry_seconds = max_retry_seconds

    def process(self, product_id, *, force=False):
        with connection(self.database_path) as conn:
            job = conn.execute("SELECT * FROM product_index_jobs WHERE product_id=?", (product_id,)).fetchone()
            if not job or job["status"] == "done" or (not force and job["next_attempt_at"] > time.time()):
                return "skipped"
            snapshot = dict(job)
            product = get_product(conn, product_id)
        try:
            # Expensive encoding happens outside the write transaction.
            vector = None
            if product:
                content_hash = document_hash(product)
                # Verify the vector store before loading a potentially large model.
                vector = self.vectors.get_embedding(product_id, content_hash)
                if vector is None:
                    vector = self.embeddings.encode_documents([product_document(product)])[0]
            with connection(self.database_path, write=True) as conn:
                current_job = conn.execute("SELECT * FROM product_index_jobs WHERE product_id=?", (product_id,)).fetchone()
                current = get_product(conn, product_id)
                if not current_job or current_job["status"] == "done" or current_job["revision"] != snapshot["revision"] or current_job["operation"] != snapshot["operation"]:
                    return "skipped"
                if current and (not product or current["search_revision"] != product["search_revision"]):
                    return "skipped"
                # Serialize the external write with SQL mutations to prevent stale writes.
                # If the process dies after Qdrant commits, the pending job safely retries.
                if current:
                    self.vectors.upsert(current, vector, document_hash(current))
                else:
                    self.vectors.delete(product_id)
                conn.execute("UPDATE product_index_jobs SET status='done', error=NULL, next_attempt_at=0, updated_at=datetime('now') WHERE product_id=?", (product_id,))
            return "done"
        except Exception as exc:
            logger.exception("Product indexing failed for %s", product_id)
            with connection(self.database_path, write=True) as conn:
                attempts = snapshot["attempts"] + 1
                conn.execute("""UPDATE product_index_jobs
                    SET status='failed', attempts=?, error=?, next_attempt_at=?, updated_at=datetime('now')
                    WHERE product_id=? AND revision=? AND operation=? AND status != 'done'
                """, (attempts, type(exc).__name__, time.time()+min(self.max_retry_seconds, 2**min(attempts, 20)),
                      product_id, snapshot["revision"], snapshot["operation"]))
            return "failed"

    def run_once(self, limit=100, *, force=False):
        with connection(self.database_path) as conn:
            ids = [r[0] for r in conn.execute("""SELECT product_id FROM product_index_jobs
                WHERE status != 'done' AND (? OR next_attempt_at <= ?)
                ORDER BY updated_at, product_id LIMIT ?""", (force, time.time(), limit))]
        counts = {"done": 0, "failed": 0, "skipped": 0}
        for product_id in ids:
            counts[self.process(product_id, force=force)] += 1
        return counts

    def run_forever(self, poll_seconds=2, batch_size=100):
        while True:
            self.run_once(batch_size)
            time.sleep(poll_seconds)
