"""One way to build an agent, so every agent gets the same guarantees:
cached model (invariant 1), fixed seed and temperature, JSON output schema."""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.genai import types
from pydantic import BaseModel

from revamp.llm.registry import family_for, model_for

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
               override: BaseLlm | None = None) -> LlmAgent:
    family = "scripted" if override is not None else family_for(name, mode)
    text = instruction.strip() + "\n" + COMMON_RULES
    if family == "local":
        # qwen3 "thinks" at length before answering by default; on a CPU that costs
        # minutes per call. /no_think switches that off for structured tasks.
        text = "/no_think\n" + text
    return LlmAgent(
        name=name,
        model=model_for(name, seed=seed, mode=mode, override=override),
        instruction=text,
        output_schema=schema,
        output_key=f"{name}_out",
        tools=tools or [],
        generate_content_config=types.GenerateContentConfig(temperature=TEMPERATURE),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
