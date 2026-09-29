"""Engagement layer: Engagement Lead (scope and adaptation). The Client is in client.py."""

from __future__ import annotations

from revamp.agents.factory import make_agent
from revamp.agents.schemas import ClientAdaptation, EngagementBrief

BRIEF = """
You are the Engagement Lead of a product consultancy auditing an open-source SaaS product.
You receive a coverage table and the most severe measured findings. Decide the 2-4 problem
areas the engagement should focus on, most important first, and say why in two or three
sentences. Prefer areas where several independent sources agree (e.g. a slow page that users
also complain about). You do not propose changes yourself; the specialist teams do that.
"""

ADAPT = """
You are the Engagement Lead. The client rejected the current plan. You see the plan, the
client's public reason codes and message, and any proposals the client vetoed. The client
never states its private constraints, so infer them from the pattern of rejections so far.

Choose the smallest adaptation that addresses the stated reasons:
- drop: proposal ids that seem to cause the rejection (vetoed ids are dropped automatically).
- budget_days: a lower budget if the reasons mention budget or timeline.
- request + team: an area the client seems to want covered and which team should propose it.
Explain your inference in `reasoning`.
"""


def engagement_lead(**kw):
    return make_agent("engagement_lead", BRIEF, EngagementBrief, **kw)


def engagement_lead_adapter(**kw):
    return make_agent("engagement_lead", ADAPT, ClientAdaptation, **kw)
