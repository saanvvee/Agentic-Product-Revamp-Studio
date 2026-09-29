"""Tool runners: measure something, return Findings. No LLM calls in here.

Each runner is a plain async function. The MCP server (revamp/mcp_server.py) exposes
them to agents; tests and scripts can call them directly.
"""
