"""Arm A0: one LLM, the same evidence, asked for a plan. No teams, no arbitration.

This is the baseline the synopsis promises: "a single LLM given the same audit data and
asked for a plan". It gets the strongest model (Gemini in hybrid mode) and the same
budget in the prompt, so any gap to the full system is not a model-size artefact.
"""

from __future__ import annotations

from revamp.agents.factory import make_agent
from revamp.agents.schemas import SingleLlmPlan

INSTRUCTION = """
You are a senior product consultant. From the measured evidence below, write a sequenced
revamp plan for this product that fits the engineering budget. For each item: title,
concrete change, cited finding ids, cost in engineer-days, impact 1-10, 1-3 area names
(lowercase), and an execution order (1 = first). Keep the total cost within the budget.
At most 15 items.
"""


def single_llm(**kw):
    return make_agent("single_llm_baseline", INSTRUCTION, SingleLlmPlan, **kw)
