# Performance measurements

![CPU/GPU embeddings](performance/embedding-comparison.svg)

## Same-query CPU/GPU comparison

| Configuration | Warm median | Warm p95 | Queries/s | Peak RAM | Peak CUDA allocation | Mean CPU* |
|---|---:|---:|---:|---:|---:|---:|
| CPU · batch 1 | 231.53 ms | 290.12 ms | 4.27 | 1586.7 MiB | — | 197.6% |
| GPU · batch 1 | 23.87 ms | 41.51 ms | 36.82 | 1964.5 MiB | 1288.9 MiB | 100.7% |
| GPU · batch 8 | 6.48 ms | 8.25 ms | 147.17 | 1936.3 MiB | 1293.6 MiB | 106.2% |

GPU single-query warm median was **9.70× faster** in this benchmark. CPU/GPU cosine agreement exceeded 0.99999988 (float32 rounding can report1.0). Batch8 timing is amortized; it excludes waiting to accumulate a batch and is not individual-user latency.

*CPU100% means one occupied logical core. RSS and whole-device GPU observations are sampled; device metrics include other processes. Each process warmed the same20 queries repeated3times, with a separate startup query. Peak RAM includes model initialization. GPU allocation/reservation comes from PyTorch. These are worker measurements, not whole-stack requirements.

## Agent/cloud bottleneck

The100-case source GPU baseline recorded **607 LLM calls**. Their summed durations accounted for **98.6%** of summed per-case elapsed time, including network/provider wait. Cases overlap across2workers, so these sums are not experiment wall time. Recorded usage: **1,523,226 input tokens**, **182,161 output tokens**; usage is available on 607/607 calls. No invoice/currency cost is inferred.

The main gpt-oss:120b model is hosted on Ollama Cloud. Local GPU resources are used for BGE, not for a120B local model. The public portable image uses CPU embeddings; the native CUDA setup is measured separately. GPU embedding speedup is not an equal whole-agent speedup.

## Implementation changes and limits

- BGE weights are pinned and bundled in the candidate image, avoiding a first-run model download.
- Provisioning runs in a short-lived process so its model memory is released before the server starts. The existing per-process model cache avoids repeated loads.
- Current user cart instructions are retained across delegation; owned SQL delivery status avoids unnecessary review clarification. Explicit quote preparation does not authorize checkout.
- CPU/GPU benchmarks are complete. Final candidate quality, full-stack CPU/RAM and reproducible release status are reported separately; no GPU container or universal compatibility claim.

## Reproduce

```bash
python -m scripts.performance.benchmark_embeddings --device cpu --batch-size 1 --output .release-local/performance/cpu-batch1
# Run these with the CUDA environment:
python -m scripts.performance.benchmark_embeddings --device cuda --batch-size 1 --output .release-local/performance/cuda-batch1
python -m scripts.performance.benchmark_embeddings --device cuda --batch-size 8 --output .release-local/performance/cuda-batch8
python -m scripts.performance.build_report
```

[Machine-readable measurements](performance/measurements.json). Raw vectors and full agent traces stay ignored.
