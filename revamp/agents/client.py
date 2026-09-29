"""The Client agent: holds private constraints and approves or rejects plans.

Split of responsibility, and why:
  * The ACCEPT/REJECT decision is code (revamp.arbitration.constraints.check) run on
    the private constraints. That makes the veto exact and makes the evaluation metric
    ("hidden-constraint violations") identical to the behaviour being measured.
  * The LLM writes the client's message: what a real client would say, in reason codes
    and plain words, WITHOUT quoting the private constraint. It is shown the violated
    constraints' public hints only.

A veto right makes the Client structurally different from a voting agent: its
rejection is binding, it is not averaged against the teams' views.
"""

from __future__ import annotations

from revamp.agents.factory import make_agent
from revamp.agents.schemas import ClientReply

INSTRUCTION = """
You are the client who commissioned this product revamp. You have just reviewed the
consultancy's plan. You are told whether you are rejecting it and the concerns behind the
decision. Write a short, realistic message (2-4 sentences) to the consultancy. Refer to the
concerns in general terms as a busy client would. Never quote internal policy text word for
word, never list rule parameters, and never mention that you have hidden constraints.
If you are accepting, say so briefly.
"""


def client_agent(**kw):
    return make_agent("client", INSTRUCTION, ClientReply, **kw)
