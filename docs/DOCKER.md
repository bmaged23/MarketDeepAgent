# Docker setup

The tested public image is [bmaged23/market-deep-agent](https://hub.docker.com/r/bmaged23/market-deep-agent). The complete evaluation, publication and public pull/smoke checks passed on 23 October 2026; exact commit and digest are in [release evidence](RELEASE_VERIFICATION.md).

The Linux amd64 CPU image contains the FastAPI application, storefront assets, seeded 100-product catalog, indexing tools, SQLite migrations and pinned BGE model weights. It contains no API keys, user database or private evaluation traces. A fresh model download and repository clone are not required. BGE's upstream model card declares MIT licensing and its README is included with the pinned weights.

## Two files, then run

```bash
mkdir market-deep-agent
cd market-deep-agent
curl -fL https://raw.githubusercontent.com/bmaged23/MarketDeepAgent/main/docker-compose.yml -o docker-compose.yml
curl -fL https://raw.githubusercontent.com/bmaged23/MarketDeepAgent/main/.env.example -o .env
```

Edit `.env` to set `OLLAMA_API_KEY`, an accessible `OLLAMA_MODEL` and optionally `ADMIN_API_KEY` for administration. You supply your own cloud account; the 120B LLM is not bundled or hosted locally.

```bash
docker pull bmaged23/market-deep-agent:cpu
docker compose up -d
docker compose logs -f market
```

Open http://localhost:8600 and register/sign in. API docs: http://localhost:8600/docs. Startup waits for Qdrant, initializes only an empty SQL catalog, reconciles/indexes vectors, releases provisioning model memory and starts the server and synchronization watcher. Initial indexing may take time on CPU. Compose explicitly sets container paths, CPU device and internal Qdrant address.

`/healthz` is process liveness. `/readyz` checks actual local embeddings, catalog size and vector count. Neither endpoint guarantees that the cloud key can access the selected model; real agent evaluations test that separately.

## Data, updates and cleanup

Named volumes hold `/app/storage` and Qdrant storage. Bundled seed assets stay in the image so updates do not mount an old copy of source code over them. A nonempty catalog is preserved on restart; it is not silently reset to the seed.

```bash
docker compose down
# Upgrade without deleting volumes:
docker compose pull
docker compose up -d
```

Only use `docker compose down -v` when intentionally erasing accounts, carts, orders, conversations and vectors. The tests use uniquely named disposable resources, not your regular Qdrant instance.

## CPU and GPU

The public portable image uses CPU embeddings and needs no NVIDIA hardware. Native CUDA 12.4 inference and resource comparison are verified separately. A GPU build stage is included for future verification but no tested public GPU image is claimed. Allow at least 8 GB available RAM and 8 GB free disk as an initial CPU budget; runtime peaks depend on concurrent model processes. Native Windows/macOS/ARM behavior is not universally certified.

For source development,`docker/compose.storage.yml` starts only Qdrant on localhost:6335. The root `docker-compose.yml` runs the complete packaged application. See the main README for native GPU setup.

## Container verification

```bash
python -m scripts.release.smoke_image --image bmaged23/market-deep-agent:cpu
```

This creates a separate network, SQL volume and Qdrant container. It checks real inference/search, UI/API routes, signup/session/CSRF, cart totals, quote-only stock preservation, confirmed cash-on-delivery checkout, idempotent retry, exact stock deduction and persistence across replacement containers. It removes only its own resources. It is distinct from the 100-case live-agent evaluation.

## Troubleshooting

- Start Docker Desktop/Engine and enable Linux containers. For WSL integration errors, verify the daemon first; never delete VHDX files or use factory reset as a routine fix.
- Check real C-drive capacity on Windows. WSL's large virtual free-space number does not guarantee Windows can grow its disk. Low disk can interrupt image exports.
- If port8600 is busy, edit only the host port in Compose.
- Inspect startup logs when readiness is503. Do not claim a healthy process has a complete index.
- Provider authentication/model errors require a valid account-accessible model/key; the image does not buy credits.
- Use the internal Qdrant address in Compose; container localhost does not point at the host service.
