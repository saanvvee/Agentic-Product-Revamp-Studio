"""Per-run objects that must NOT live in ADK session state.

Session state is shared by every node and has no access control (verified in ADK
2.9), and it must be JSON-serialisable. So state holds only plain, non-secret values
(ids, counters, the current budget). Everything else hangs off a RunContext looked
up by run_id:

  * team_kb   - KB handle with role "team"   (cannot read client_private)
  * client_kb - KB handle with role "client" (used ONLY by the client node)
  * crew      - builds each agent once per run, on first use
  * record    - the RunRecord being filled in, including the cost ledger
"""

from __future__ import annotations

from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm

from revamp.agents import arbitration, baseline, client, engagement, perspective, teams
from revamp.contracts import Plan, Proposal, RunRecord
from revamp.kb import KnowledgeBase
from revamp.products import Product
from revamp.workflow.arms import Arm

_BUILDERS = {
    "engagement_lead": engagement.engagement_lead,
    "engagement_adapter": engagement.engagement_lead_adapter,
    "voice_of_customer": perspective.voice_of_customer,
    "journey_auditor": perspective.journey_auditor,
    "design": lambda **kw: teams.team("design", **kw),
    "engineering": lambda **kw: teams.team("engineering", **kw),
    "product_pricing": lambda **kw: teams.team("product_pricing", **kw),
    "handoff_reviewer": teams.handoff_reviewer,
    "conflict_detector": arbitration.conflict_detector,
    "red_team": arbitration.red_team,
    "client": client.client_agent,
    "single_llm": baseline.single_llm,
}


@dataclass
class Crew:
    seed: int = 0
    mode: str | None = None
    # Test hook: agent key -> fake model. Still wrapped in CachedLlm by the factory.
    overrides: dict[str, BaseLlm] = field(default_factory=dict)
    _agents: dict[str, LlmAgent] = field(default_factory=dict)

    def get(self, key: str) -> LlmAgent:
        if key not in self._agents:
            self._agents[key] = _BUILDERS[key](seed=self.seed, mode=self.mode,
                                               override=self.overrides.get(key))
        return self._agents[key]


@dataclass
class RunContext:
    run_id: str
    product: Product
    arm: Arm
    seed: int
    team_kb: KnowledgeBase
    client_kb: KnowledgeBase
    crew: Crew
    record: RunRecord
    hitl: bool = False  # pause for human approval of high-impact items (B10)
    proposals: dict[str, Proposal] = field(default_factory=dict)  # current, by id
    current_plan: Plan | None = None
    pending_approval: dict | None = None  # set while paused for human approval
    stats: dict[str, int] = field(default_factory=dict)  # citation / red-team counters
    log: list[str] = field(default_factory=list)  # human-readable trace for the report

    def note(self, msg: str) -> None:
        self.log.append(msg)


_RUNS: dict[str, RunContext] = {}


def register(rc: RunContext) -> None:
    _RUNS[rc.run_id] = rc


def get(run_id: str) -> RunContext:
    return _RUNS[run_id]


def release(run_id: str) -> None:
    _RUNS.pop(run_id, None)
