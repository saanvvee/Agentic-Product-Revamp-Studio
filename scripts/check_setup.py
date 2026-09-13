"""Verify this clone is set up correctly. Run it after cloning, and in CI.

Exists because README instructions get skimmed. The pre-commit hook is the only
thing standing between this public repository and NC-licensed dataset
derivatives, and it is per-clone configuration that git does NOT distribute --
so two of three teammates can have it unset and nobody would know until the
licence violation is already pushed.

Usage:
    python scripts/check_setup.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=REPO_ROOT, check=False
        ).stdout.strip()
    except FileNotFoundError:
        return ""


def check_hooks_path() -> tuple[bool, str]:
    """THE important one. R17 has nearly fired twice from unpredicted paths."""
    configured = _git("config", "core.hooksPath")
    if configured == "scripts":
        return True, "core.hooksPath=scripts"
    return False, (
        f"core.hooksPath is {configured or 'UNSET'}, so the pre-commit hook is "
        "NOT running.\n"
        "         This repo is public and MVTec AD is CC BY-NC-SA. Without the\n"
        "         hook, nothing stops dataset bytes or an API key being pushed.\n"
        "         FIX:  git config core.hooksPath scripts"
    )


def check_hook_executable() -> tuple[bool, str]:
    hook = REPO_ROOT / "scripts" / "pre-commit"
    if not hook.is_file():
        return False, "scripts/pre-commit is missing"
    return True, "scripts/pre-commit present"


def check_python_version() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    if (major, minor) == (3, 11):
        return True, f"Python {major}.{minor}"
    return False, (
        f"running Python {major}.{minor}, but this project targets 3.11 "
        "(see .python-version).\n"
        "         Activate the venv:  .venv/Scripts/activate"
    )


def check_gitignore_covers_datasets() -> tuple[bool, str]:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    required = ["data/", "datasets/", "artifacts/", ".env", "cache/"]
    missing = [entry for entry in required if entry not in text]
    if missing:
        return False, f".gitignore is missing: {missing}"
    return True, "gitignore covers data/, datasets/, artifacts/, .env, cache/"


def check_no_tracked_dataset_bytes() -> tuple[bool, str]:
    """Belt and braces: the hook blocks new ones, this catches history."""
    tracked = _git("ls-files")
    offenders = [
        line
        for line in tracked.splitlines()
        if line.lower().endswith((".png", ".jpg", ".wav", ".ckpt", ".pt", ".pth"))
        and not line.startswith(("tests/fixtures/", "docs/img/"))
    ]
    if offenders:
        return False, f"dataset bytes are already tracked: {offenders[:5]}"
    return True, "no dataset bytes tracked"


def check_env_file() -> tuple[bool, str]:
    """A warning, not a failure: the Ollama path needs no key."""
    if (REPO_ROOT / ".env").is_file():
        return True, ".env present"
    return True, (
        ".env absent -- fine for the local Ollama path, but Gemini-backed agents\n"
        "         will not run. Copy config/default.env to .env when you have a key."
    )


CHECKS = [
    ("pre-commit hook enabled", check_hooks_path),
    ("pre-commit hook present", check_hook_executable),
    ("Python version", check_python_version),
    ("gitignore coverage", check_gitignore_covers_datasets),
    ("no tracked dataset bytes", check_no_tracked_dataset_bytes),
    ("environment file", check_env_file),
]


def main() -> int:
    print("Setup check\n")
    failures = 0

    for label, check in CHECKS:
        ok, detail = check()
        print(f"  [{'ok' if ok else 'XX'}] {label:28} {detail}")
        if not ok:
            failures += 1

    print()
    if failures:
        print(f"{failures} problem(s) found. Fix them before committing.")
        return 1
    print("Setup is correct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
