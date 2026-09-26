"""App-level configuration from environment variables.

LLM settings (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_TIMEOUT) are read
by src/ai/provider.py at request time.
"""

import os
from pathlib import Path

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def target_db_path() -> Path:
    """The SQLite target (warehouse) database that uploads are loaded into."""
    return Path(os.getenv("TARGET_DB_PATH") or DATA_DIR / "target.db")
