"""Compatibility entry point. Prefer: python -m uvicorn app.main:app --port 8600."""
from pathlib import Path
import sys

# Also preserve `uvicorn main:app` when launched from UI/backend.
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.main import app  # noqa: E402, F401
