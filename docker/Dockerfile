# syntax=docker/dockerfile:1
ARG DEVICE=cpu
FROM python:3.12.15-slim-bookworm AS cpu-deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements/runtime.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt && pip check
FROM python:3.12.15-slim-bookworm AS gpu-deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements/gpu.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu124 -r /tmp/requirements.txt && pip check
FROM cpu-deps AS model-assets
COPY docker/download_model.py /tmp/download_model.py
RUN python /tmp/download_model.py
FROM ${DEVICE}-deps AS application
LABEL org.opencontainers.image.source="https://github.com/bmaged23/MarketDeepAgent"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
    EMBEDDING_CACHE_DIR=/opt/model-cache DATABASE_PATH=/app/storage/products.db \
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
WORKDIR /app
COPY --from=model-assets /opt/model-cache /opt/model-cache
COPY app/ app/
COPY UI/ UI/
COPY products/ products/
COPY data/seed_products.py data/catalog_nutrition.json data/
COPY scripts/ scripts/
COPY evaluation/ evaluation/
RUN useradd --uid 10001 --create-home market && mkdir /app/storage && chown -R market:market /app/storage /app/data
USER market
EXPOSE 8600
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/healthz',timeout=5)"
CMD ["python", "-m", "scripts.runtime.serve"]
