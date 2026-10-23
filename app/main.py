from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from app.utils.errors import ServiceError
from app.config import PROJECT_ROOT, get_settings
from app.database.connection import migrate
from app.products.routes import router as products_router
from app.products.service import ProductService
from app.customers.routes import router as customers_router
from app.customers.service import CustomerService
from app.orders.routes import router as orders_router
from app.orders.service import OrderService
from app.product_search.routes import router as search_router
from app.agents.retrieval.routes import router as retrieval_router
from app.product_search.service import create_search_service
from app.model_clients.factory import embedding_client, vector_index
from app.authentication.service import SessionService
from app.authentication.routes import router as session_router
from app.cart.service import CartService
from app.cart.routes import router as cart_router
from app.conversations.service import ConversationService
from app.customer_memory.service import MemoryService
from app.customer_memory.vector_index import MemoryVectorIndex
from app.assistant.service import AssistantService
from app.assistant.routes import router as assistant_router



def create_app(settings=None, embeddings=None, vectors=None, memory_vectors=None, assistant_runner_factory=None):
    settings = settings or get_settings()
    embeddings = embeddings or embedding_client(settings)
    vectors = vectors or vector_index(settings)
    memory_vectors = memory_vectors or MemoryVectorIndex(settings)

    @asynccontextmanager
    async def lifespan(app):
        migrate(settings.database_path)
        try:
            yield
        finally:
            vectors.close()
            memory_vectors.close()

    app = FastAPI(title="SmartCart API", lifespan=lifespan)
    @app.get("/healthz", include_in_schema=False)
    def health():
        # Process liveness only; this does not certify cloud credentials or retrieval.
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def ready():
        # Verify actual local inference/storage; cloud account access is tested separately.
        try:
            from app.database.connection import connection
            with connection(settings.database_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
            info = vectors.client.get_collection(settings.qdrant_collection)
            vector = embeddings.encode_query("catalog readiness")
            if count < 1 or (info.points_count or 0) < count or len(vector) != settings.embedding_dim:
                raise ValueError("Catalog or vector index is incomplete")
            return {"status": "ready", "products": count, "embedding_device": settings.embedding_device,
                    "cloud_credentials_configured": bool(settings.ollama_api_key.get_secret_value())}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})

    @app.exception_handler(ServiceError)
    async def service_error_handler(request, error):
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    app.state.settings = settings
    app.state.products = ProductService(settings.database_path, PROJECT_ROOT)
    app.state.customers = CustomerService(settings.database_path)
    app.state.orders = OrderService(settings.database_path)
    app.state.search = create_search_service(settings, embeddings, vectors)
    app.state.sessions = SessionService(settings)
    app.state.cart = CartService(settings.database_path, settings.cart_quote_ttl_seconds, settings.cart_max_items)
    app.state.conversations = ConversationService(settings)
    app.state.memory = MemoryService(settings, embeddings, memory_vectors)
    app.state.assistant = AssistantService(settings, app.state.search, app.state.conversations, app.state.memory, assistant_runner_factory)
    for router in (products_router, customers_router, orders_router, search_router, retrieval_router, session_router, cart_router, assistant_router):
        app.include_router(router)
    app.mount("/products", StaticFiles(directory=PROJECT_ROOT / "products"), name="products")
    app.mount("/", StaticFiles(directory=PROJECT_ROOT / "UI/frontend", html=True), name="frontend")
    return app


app = create_app()
