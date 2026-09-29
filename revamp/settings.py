"""All configuration in one place, read once from the environment (.env).

Agents and tools import `settings` instead of reading os.environ themselves, so a
viva question like "where does the model name come from?" has one answer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    root: Path
    gemini_model: str
    local_model: str
    model_mode: str  # "hybrid" | "local" | "gemini"
    cache_dir: Path
    cache_read_only: bool
    llm_concurrency: int
    github_token: str
    psi_api_key: str
    phoenix_endpoint: str
    workspace_dir: Path
    runs_dir: Path
    products_dir: Path
    tools_bin: Path
    kb_path: Path


def load() -> Settings:
    return Settings(
        root=ROOT,
        gemini_model=os.getenv("REVAMP_GEMINI_MODEL", "gemini-2.5-flash"),
        local_model=os.getenv("REVAMP_LOCAL_MODEL", "ollama_chat/qwen3:4b"),
        model_mode=os.getenv("REVAMP_MODEL_MODE", "hybrid"),
        cache_dir=ROOT / os.getenv("REVAMP_CACHE_DIR", "cache/llm"),
        cache_read_only=_flag("REVAMP_CACHE_READ_ONLY"),
        # Invariant 5: never more than 3 LLM calls in flight.
        llm_concurrency=3,
        github_token=os.getenv("GITHUB_TOKEN", ""),
        psi_api_key=os.getenv("PSI_API_KEY", ""),
        phoenix_endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", ""),
        workspace_dir=ROOT / "workspace",
        runs_dir=ROOT / "runs",
        products_dir=ROOT / "products",
        tools_bin=ROOT / "tools" / "bin",
        kb_path=ROOT / "runs" / "kb.sqlite3",
    )


settings = load()
