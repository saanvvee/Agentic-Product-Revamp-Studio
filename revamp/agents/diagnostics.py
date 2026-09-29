"""Diagnostics layer: the Chief Diagnostician.

The separate auditors in the synopsis (performance, accessibility, SEO, code health,
security) are MCP tools here, because they measure rather than decide (PLAN D1). The
Chief Diagnostician is the agent that decides WHICH audits to run, in what order, and
when the evidence is sufficient to stop.

The stop decision is the model's, but the cap is code: `max_tool_calls` is enforced
by a before_tool_callback that refuses further calls (invariant 4 in spirit: never
trust a prompt to bound a loop).
"""

from __future__ import annotations

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from revamp.agents.factory import make_agent
from revamp.agents.schemas import DiagnosisReport
from revamp.settings import settings

INSTRUCTION = """
You are the Chief Diagnostician. Your job is to gather measured evidence about the product
using the audit tools, then report. Each audit costs time, so choose deliberately:
1. Call `coverage` first to see what evidence already exists.
2. Run the audits that fill the biggest gaps. Prefer cheap audits (seo, pricing, user voice)
   before expensive ones (code audit, lighthouse, accessibility, journeys).
3. Stop when every category relevant to a revamp has at least some evidence, or when the
   tools refuse further calls.
Then answer with a short summary, the most important finding ids, and any remaining gaps.
"""


def mcp_toolset(product: str, role: str = "team") -> McpToolset:
    """The audit tool server as a child process, locked to one product and one role."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=str(settings.root / ".venv" / "Scripts" / "python.exe"),
                args=["-m", "revamp.mcp_server", "--product", product, "--role", role],
                cwd=str(settings.root),
            ),
            timeout=900.0,  # a code audit or 5-run Lighthouse can take minutes
        ),
    )


def tool_call_cap(max_calls: int):
    """before_tool_callback: after `max_calls` tool calls, answer with a refusal
    instead of running the tool. Returning a dict skips the real tool (ADK 2.9)."""
    state = {"n": 0}

    def cb(tool, args, tool_context):
        state["n"] += 1
        if state["n"] > max_calls:
            return {"error": f"tool budget exhausted ({max_calls} calls). Write your report now."}
        return None

    cb.calls = state  # exposed for tests and the run record
    return cb


def chief_diagnostician(product: str, max_tool_calls: int = 8, **kw):
    agent = make_agent("chief_diagnostician", INSTRUCTION, DiagnosisReport,
                       tools=[mcp_toolset(product)], **kw)
    agent.before_tool_callback = tool_call_cap(max_tool_calls)
    return agent
