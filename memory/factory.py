"""Composition root for the memory seam.

The only module allowed to import a concrete store. Ablation A3 is expressed here
as `enabled=false` in config, so the workflow runs identical code either way and
any difference in results is attributable to memory alone (PRD S12.2).
"""

from __future__ import annotations

from core.config import Settings
from memory.base import MemoryStore


def build_memory_store(settings: Settings) -> MemoryStore:
    if not settings.memory.enabled:
        # ABLATION A3. Not a code branch in the workflow -- a different object
        # behind the same seam. The orchestrator, critic, and guardrail never
        # learn that memory is off.
        from memory.in_memory import DisabledStore

        return DisabledStore()

    match settings.memory.impl:
        case "sqlite":
            from memory.sqlite_store import SqliteStore

            return SqliteStore(settings.memory.db_path)

        case "in_memory":
            from memory.in_memory import InMemoryStore

            return InMemoryStore()

        case unknown:  # pragma: no cover - Literal makes this unreachable
            raise ValueError(f"unknown memory impl: {unknown!r}")
