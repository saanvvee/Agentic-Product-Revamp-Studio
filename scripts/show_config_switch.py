"""Demonstrate that one config line switches the implementation behind a seam.

Run:  .venv/Scripts/python.exe scripts/show_config_switch.py

This exists because "swapping is one line in config" is a claim, and a claim
about architecture is worth exactly as much as the demonstration behind it. The
same assertion is made in tests/test_llm_seam.py; this script is the version you
can show someone in a viva.
"""

from __future__ import annotations

import os

from core.config import Settings
from core.llm.factory import build_llm_provider


def build_with(**env: str):
    """Build a provider under a temporary environment, then restore it."""
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        settings = Settings()
        provider = build_llm_provider(settings)
        inner = getattr(provider, "_inner", None)
        wrapper = type(provider).__name__ if inner is not None else "(none)"
        target = inner if inner is not None else provider
        return wrapper, type(target).__name__, target.model_id
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def main() -> None:
    print("The LLM seam: one env var, three different systems.\n")
    print(f"{'IRA_LLM__PROVIDER':<22} {'wrapper':<16} {'implementation':<18} model_id")
    print("-" * 82)

    for provider in ("stub", "ollama"):
        wrapper, inner, model_id = build_with(
            IRA_LLM__PROVIDER=provider, IRA_LLM__CACHED="true"
        )
        print(f"{provider:<22} {wrapper:<16} {inner:<18} {model_id}")

    # Gemini needs a key; show what happens without one rather than skipping it,
    # because failing loudly at construction IS the designed behaviour.
    try:
        wrapper, inner, model_id = build_with(
            IRA_LLM__PROVIDER="gemini", IRA_LLM__CACHED="true"
        )
        print(f"{'gemini':<22} {wrapper:<16} {inner:<18} {model_id}")
    except ValueError as exc:
        print(f"{'gemini':<22} not built: {str(exc)[:44]}")

    print("\nCaching is orthogonal -- it wraps whichever provider was chosen:")
    for cached in ("true", "false"):
        wrapper, inner, _ = build_with(
            IRA_LLM__PROVIDER="stub", IRA_LLM__CACHED=cached
        )
        described = f"{wrapper} wrapping {inner}" if wrapper != "(none)" else f"{inner}, uncached"
        print(f"  IRA_LLM__CACHED={cached:<6} -> {described}")

    print(
        "\nNo agent imports any of these classes. They receive an LLMProvider by\n"
        "constructor injection, which is what makes ablation A5 (all-Gemini) a\n"
        "configuration rather than a second copy of the system."
    )


if __name__ == "__main__":
    main()
