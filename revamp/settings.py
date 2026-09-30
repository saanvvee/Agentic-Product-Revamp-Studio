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
    ollama_api_base: str
    ollama_models: dict[str, str]  # tier -> Ollama tag: instruct | thinking | vision
    ollama_num_ctx: dict[str, int]  # tier -> context window
    ollama_num_gpu: int  # layers offloaded to GPU; 999 = all (force GPU), -1 = Ollama decides
    ollama_keep_alive: str  # keep models loaded between calls (avoids reload per call)
    llm_timeout: int  # seconds per model call
    local_tier_overrides: dict[str, str]  # agent route -> tier, from REVAMP_LOCAL_TIERS
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
    client_url: str  # A2A Client service; empty = in-process client


def _instruct_default() -> str:
    # Back-compat: REVAMP_LOCAL_MODEL (ollama_chat/<tag>) used to name the one local model.
    legacy = os.getenv("REVAMP_LOCAL_MODEL", "")
    if legacy:
        return legacy.split("/", 1)[-1]
    return "qwen3:4b-instruct-2507-q4_K_M"


def _tier_overrides() -> dict[str, str]:
    """REVAMP_LOCAL_TIERS="red_team=instruct,design=thinking" moves agents between tiers."""
    out = {}
    for pair in os.getenv("REVAMP_LOCAL_TIERS", "").split(","):
        if "=" in pair:
            agent, tier = (x.strip() for x in pair.split("=", 1))
            out[agent] = tier
    return out


def load() -> Settings:
    return Settings(
        root=ROOT,
        gemini_model=os.getenv("REVAMP_GEMINI_MODEL", "gemini-2.5-flash"),
        ollama_api_base=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
        # Explicit tags on purpose: in the Ollama library "qwen3:4b" and "qwen3-vl:4b"
        # both resolve to THINKING variants (checked against registry digests, 30 Sep).
        ollama_models={
            "instruct": os.getenv("REVAMP_OLLAMA_INSTRUCT", _instruct_default()),
            "thinking": os.getenv("REVAMP_OLLAMA_THINKING", "qwen3:4b-thinking-2507-q4_K_M"),
            "vision": os.getenv("REVAMP_OLLAMA_VISION", "qwen3-vl:4b-instruct"),
        },
        # Our prompts are ~2-4k tokens plus a ~1.5k answer; 4096 would silently cut the
        # start of the prompt. Thinking needs room for its reasoning tokens; images cost
        # tokens too.
        ollama_num_ctx={
            "instruct": int(os.getenv("REVAMP_NUM_CTX", "8192")),
            "thinking": int(os.getenv("REVAMP_NUM_CTX_THINKING", "16384")),
            "vision": int(os.getenv("REVAMP_NUM_CTX_VISION", "16384")),
        },
        ollama_num_gpu=int(os.getenv("REVAMP_OLLAMA_NUM_GPU", "999")),
        ollama_keep_alive=os.getenv("REVAMP_OLLAMA_KEEP_ALIVE", "30m"),
        llm_timeout=int(os.getenv("REVAMP_LLM_TIMEOUT", "900")),
        local_tier_overrides=_tier_overrides(),
        model_mode=os.getenv("REVAMP_MODEL_MODE", "local"),
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
        client_url=os.getenv("REVAMP_CLIENT_URL", ""),
    )


settings = load()
