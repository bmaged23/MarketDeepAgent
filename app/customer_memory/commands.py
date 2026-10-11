import argparse
import json
from app.config import get_settings
from app.database.connection import migrate
from app.customer_memory.service import MemoryService
from app.customer_memory.vector_index import MemoryVectorIndex
from app.model_clients.factory import embedding_client


def main():
    parser=argparse.ArgumentParser(description="Synchronize queued customer memories to Qdrant")
    parser.add_argument('--limit',type=int,default=100)
    args=parser.parse_args()
    if args.limit<1: parser.error('--limit must be positive')
    settings=get_settings()
    migrate(settings.database_path)
    vectors=MemoryVectorIndex(settings)
    try: print(json.dumps(MemoryService(settings,embedding_client(settings),vectors).sync(limit=args.limit)))
    finally: vectors.close()


if __name__=='__main__': main()
