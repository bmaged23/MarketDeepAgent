"""Short-lived provisioning process; releases model RAM/VRAM before serving."""
import subprocess,sys,time
from app.config import get_settings
from app.database.connection import migrate,connection
from app.model_clients.factory import embedding_client,vector_index
from app.product_indexing.processor import IndexingProcessor
from app.product_indexing.service import reconcile

def main():
    settings=get_settings();settings.database_path.parent.mkdir(parents=True,exist_ok=True)
    migrate(settings.database_path)
    with connection(settings.database_path) as c:empty=c.execute('SELECT COUNT(*) FROM product').fetchone()[0]==0
    if empty:subprocess.run([sys.executable,'data/seed_products.py'],check=True)
    vectors=vector_index(settings);embeddings=embedding_client(settings)
    try:
        for attempt in range(30):
            try:vectors.ensure_collection();break
            except Exception:
                if attempt==29:raise
                time.sleep(2)
        reconcile(settings.database_path,vectors)
        processor=IndexingProcessor(settings.database_path,embeddings,vectors)
        # A seed contains 100 products; larger catalogs are processed in bounded batches.
        while True:
            counts=processor.run_once(settings.indexing_batch_size,force=True)
            if counts['failed']:raise RuntimeError('Catalog indexing failed; inspect service logs')
            if not counts['done']:break
    finally:vectors.close()

if __name__=='__main__':main()
