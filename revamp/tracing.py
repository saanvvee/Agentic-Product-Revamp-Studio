"""Arize Phoenix tracing (self-hosted). Start a collector with `phoenix serve`, then set
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006 . Every ADK agent, tool and model
call becomes a span via the OpenInference ADK instrumentor."""

from __future__ import annotations

from revamp.settings import settings

_done = False


def setup() -> bool:
    global _done
    if _done or not settings.phoenix_endpoint:
        return _done
    from phoenix.otel import register
    register(project_name="revamp-studio", endpoint=settings.phoenix_endpoint.rstrip("/")
             + "/v1/traces", auto_instrument=True)
    _done = True
    return True
