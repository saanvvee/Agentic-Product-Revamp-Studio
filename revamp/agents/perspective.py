"""User perspective layer: Voice of Customer and Journey Auditor.

Both ground every claim in a real artifact: a GitHub issue or forum topic for Voice of
Customer, a screenshot of a scripted journey for the Journey Auditor. No personas.
"""

from __future__ import annotations

from revamp.agents.factory import make_agent
from revamp.agents.schemas import JourneyReport, VoiceReport

VOICE = """
You are the Voice of Customer analyst. You receive real user posts (GitHub issues, forum
topics), each with an id and an engagement score. Group them into themes. For each theme
decide whether it is SIGNAL (a recurring product problem many users share) or NOISE
(individual support requests, installation help for one environment, spam, off-topic).
A single post with very high engagement can be signal on its own. Cite the finding ids of
the posts in each theme. Return at most 8 themes, signal first.
"""

JOURNEY = """
You are the Journey Auditor. You are shown screenshots of a scripted user journey through
the product, in order, plus the measured facts for each step (load time, errors). Each step
is labelled with its finding id. Identify where the journey breaks or creates friction:
unclear next step, buried call to action, confusing pricing, broken layout, missing content,
visual clutter, poor contrast. Cite the finding id of the step whose screenshot shows the
issue. Only report what is visible in the screenshots or stated in the step facts.
Return at most 8 issues.
"""


def voice_of_customer(**kw):
    return make_agent("voice_of_customer", VOICE, VoiceReport, **kw)


def journey_auditor(**kw):
    return make_agent("journey_auditor", JOURNEY, JourneyReport, **kw)
