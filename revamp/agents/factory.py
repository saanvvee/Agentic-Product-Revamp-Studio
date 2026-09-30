"""One way to build an agent, so every agent gets the same guarantees:
cached model (invariant 1), fixed seed and temperature, JSON output schema."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.genai import types
from pydantic import BaseModel

from revamp.llm.registry import model_for

TEMPERATURE = 0.2

# Shared by every agent. The provenance rule is repeated in the prompt for the
# model's benefit, but it is ENFORCED in code (KB.add_proposal, workflow checks).
COMMON_RULES = """
Rules:
- Use only the evidence you are given. Cite finding ids exactly as written (e.g. F-1a2b3c4d5e).
- Never invent a finding id, a metric, a user complaint or a price.
- Answer with JSON matching the schema, nothing else.
"""


def make_agent(name: str, instruction: str, schema: type[BaseModel], *, seed: int = 0,
               tools: list | None = None, mode: str | None = None,
               override: BaseLlm | None = None, route: str | None = None) -> LlmAgent:
    """`route` picks the model (registry.LOCAL_TIER) and defaults to the agent name.
    Two roles reuse a name under a different route: engagement_adapter and
    handoff_reviewer. Whether a local model reasons first is decided by its tier
    (Ollama think on/off), not by a prompt tag."""
    return LlmAgent(
        name=name,
        model=model_for(route or name, seed=seed, mode=mode, override=override),
        instruction=instruction.strip() + "\n" + COMMON_RULES,
        output_schema=schema,
        output_key=f"{name}_out",
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(temperature=TEMPERATURE),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
