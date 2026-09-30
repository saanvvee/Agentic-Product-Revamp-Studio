"""Export OpenTelemetry traces to Langfuse and/or Arize Phoenix. No vendor SDK needed.

Langfuse ingests OTLP over HTTP at <host>/api/public/otel/v1/traces with Basic auth
(public key : secret key) and the header x-langfuse-ingestion-version: 4. We send
there directly with the OpenTelemetry exporter already in the venv, which is what
the langfuse SDK does internally.

  * Self-hosted: deploy/langfuse (Docker Compose); keys from deploy/langfuse/.env.
  * Langfuse Cloud Hobby: free, no card; set LANGFUSE_BASE_URL=https://cloud.langfuse.com.
  * Phoenix (optional, both can run): `phoenix serve`, PHOENIX_COLLECTOR_ENDPOINT.

Agent, model and tool spans come from the OpenInference ADK instrumentor; workflow
node spans and the per-run root span come from revamp/observe.py.
"""

from __future__ import annotations

import base64
import os

_provider = None


def backends() -> dict[str, dict]:
    out = {}
    host = os.getenv("LANGFUSE_BASE_URL", "").rstrip("/")
    pk, sk = os.getenv("LANGFUSE_PUBLIC_KEY", ""), os.getenv("LANGFUSE_SECRET_KEY", "")
    if host and pk and sk:
        auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
        out["langfuse"] = {"endpoint": f"{host}/api/public/otel/v1/traces",
                           "headers": {"Authorization": f"Basic {auth}",
                                       "x-langfuse-ingestion-version": "4"},
                           "ui": host}
    phoenix = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").rstrip("/")
    if phoenix:
        out["phoenix"] = {"endpoint": f"{phoenix}/v1/traces", "headers": {}, "ui": phoenix}
    return out


def setup() -> list[str]:
    """Idempotent. Returns the names of the enabled backends (empty = tracing off)."""
    global _provider
    if _provider is not None:
        return list(backends())
    conf = backends()
    if not conf:
        return []
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _provider = TracerProvider(resource=Resource.create({"service.name": "revamp-studio"}))
    for c in conf.values():
        _provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=c["endpoint"], headers=c["headers"])))
    trace.set_tracer_provider(_provider)
    GoogleADKInstrumentor().instrument(tracer_provider=_provider)
    return list(conf)


def flush() -> None:
    if _provider is not None:
        _provider.force_flush(timeout_millis=10_000)


def trace_url(trace_id: str | None) -> str | None:
    """Deep link from the dashboard into the tracing UI."""
    conf = backends()
    if not trace_id:
        return None
    if "langfuse" in conf:
        project = os.getenv("LANGFUSE_PROJECT_ID", "revamp-studio")
        return f"{conf['langfuse']['ui']}/project/{project}/traces/{trace_id}"
    if "phoenix" in conf:
        return conf["phoenix"]["ui"]
    return None
