"""What each agent must answer with. Kept small and flat: a 4B local model follows
a short schema far more reliably than a deep one.

These are LLM-facing drafts. Code turns them into the frozen contracts
(revamp/contracts.py), assigning ids and checking provenance on the way.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Sev = Literal["low", "medium", "high", "critical"]


class EngagementBrief(BaseModel):
    focus: list[str] = Field(min_length=1, max_length=4,
                             description="2-4 problem AREA NAMES (e.g. security, onboarding, "
                                         "performance), most important first. Not finding ids.")
    rationale: str
    budget_note: str = ""


class DiagnosisReport(BaseModel):
    summary: str
    key_finding_ids: list[str] = Field(description="up to 12 most important finding ids")
    gaps: list[str] = Field(default_factory=list,
                            description="evidence categories still missing or thin")


class VoiceTheme(BaseModel):
    theme: str
    is_signal: bool = Field(description="false if the items are support requests, "
                                        "one-off bugs, or off-topic")
    finding_ids: list[str] = Field(min_length=1)
    why: str


class VoiceReport(BaseModel):
    themes: list[VoiceTheme]


class JourneyIssue(BaseModel):
    screenshot_finding_id: str = Field(description="id of the step finding whose screenshot "
                                                   "shows the issue")
    issue: str
    severity: Sev
    area: str = Field(description="short area name, e.g. navigation, pricing_page, signup")


class JourneyReport(BaseModel):
    issues: list[JourneyIssue]


class ProposalDraft(BaseModel):
    ref: str = Field(description="short local reference like D1, E2, PP1")
    title: str
    change: str = Field(description="what to change, concretely")
    rationale: str = Field(description="why, referring to the cited findings")
    finding_ids: list[str] = Field(min_length=1)
    cost_days: float = Field(gt=0, le=200, description="engineer-days")
    value: int = Field(ge=1, le=10, description="expected impact 1-10")
    depends_on: list[str] = Field(default_factory=list,
                                  description="refs of your own proposals that must ship first")
    areas: list[str] = Field(min_length=1, description="1-3 area names this touches")
    risk: Literal["low", "medium", "high"] = "low"


class TeamProposals(BaseModel):
    proposals: list[ProposalDraft] = Field(max_length=6)


class HandoffDecision(BaseModel):
    proposal_id: str
    decision: Literal["accept", "reject"]
    reason: str = ""
    realistic_cost_days: float | None = None


class HandoffReview(BaseModel):
    decisions: list[HandoffDecision]


class ConflictDraft(BaseModel):
    a: str
    b: str
    kind: Literal["contradiction", "same_area_overlap"]
    explanation: str
    exclusive: bool = Field(description="true if both cannot ship as written")


class ConflictReport(BaseModel):
    conflicts: list[ConflictDraft]


class Objection(BaseModel):
    proposal_id: str
    issue: str
    action: Literal["block", "flag"] = Field(description="block only if the evidence does not "
                                                         "support the proposal at all")


class RedTeamReport(BaseModel):
    objections: list[Objection]


class ClientAdaptation(BaseModel):
    """Engagement Lead's response to a Client rejection."""
    drop: list[str] = Field(default_factory=list, description="proposal ids to remove")
    budget_days: float | None = Field(default=None, description="new, lower budget if the "
                                                                "client signalled cost or timeline")
    request: str = Field(default="", description="area the client seems to want covered, if any")
    team: Literal["design", "engineering", "product_pricing", ""] = ""
    reasoning: str


class ClientReply(BaseModel):
    message: str


class PlanDraftItem(BaseModel):
    title: str
    change: str
    finding_ids: list[str] = Field(min_length=1)
    cost_days: float = Field(gt=0, le=200)
    value: int = Field(ge=1, le=10)
    areas: list[str] = Field(min_length=1)
    order: int = Field(ge=1)


class SingleLlmPlan(BaseModel):
    items: list[PlanDraftItem] = Field(max_length=15)
    summary: str
