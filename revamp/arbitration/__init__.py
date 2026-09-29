"""Deterministic arbitration: budget allocation, sequencing, constraint checks.

These decide, but they need no LLM (PLAN D1). Keeping them as pure functions means
the evaluation's core metrics cannot be argued with by a model.
"""
