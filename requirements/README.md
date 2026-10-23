# Dependencies

Use one installation route from the repository root:

- CPU application: `python -m pip install -r requirements.txt`.
- NVIDIA CUDA 12.4 application: `python -m pip install --extra-index-url https://download.pytorch.org/whl/cu124 -r requirements/gpu.txt`.
- Lightweight offline tests: `python -m pip install -r requirements-dev.txt`.
- Judge/tracing tools: `python -m pip install -r requirements/evaluation.txt` (add to a runtime environment for live inference).

Python 3.12 is the new candidate container/runtime target; Python 3.13 is retained for lightweight regression checks. CPU and GPU locks pin all resolved dependencies and use the same application/embedding versions. `.in` files are maintainer inputs. `original-cuda-snapshot.txt` preserves the old Python 3.13 demonstration environment; it is not the default fresh install. Fresh-install, GPU and image verification status is documented separately rather than assumed from these files.
