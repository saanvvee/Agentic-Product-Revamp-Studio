"""Frozen data contracts shared by every module (PLAN M1, CLAUDE.md invariant 6).

Every agent reads and writes these shapes, and nothing else. Changing a field here is
a schema amendment: log it in PLAN.md, because three workstreams code against it.

Flow of artifacts through the system:

    tool run -> Finding -> Proposal -> Conflict -> Plan -> ClientVerdict
                  ^            |
                  +- cites ----+   (provenance: every Proposal cites Findings)

ClientConstraint is private to the Client. It lives only in the KB's
`client_private` namespace and is never placed in ADK session state.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stable_id(prefix: str, *parts: str) -> str:
    """Deterministic id from content, so re-running a tool on the same page yields
    the same Finding id and the KB deduplicates instead of piling up copies."""
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:10]
    return f"{prefix}-{digest}"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------------------------- evidence

Category = Literal[
    "performance",
    "accessibility",
    "seo",
    "security",
    "code_health",
    "user_voice",
    "journey",
    "pricing",
]
Severity = Literal["info", "low", "medium", "high", "critical"]
SEVERITY_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class Evidence(_Frozen):
    """Where a Finding came from. This is the provenance anchor: a claim without one
    of these is rejected (invariant 2)."""

    tool: str  # e.g. "psi", "axe", "osv-scanner", "github_issues"
    tool_version: str = ""
    target: str  # "live" or "local:<version>"
    locator: str  # URL, file path, issue URL, package@version
    artifact_path: str | None = None  # screenshot / raw JSON under runs/, if any
    observed_at: datetime = Field(default_factory=utcnow)


class Finding(_Frozen):
    id: str
    product: str
    category: Category
    title: str
    detail: str = ""
    severity: Severity
    metric: str | None = None  # e.g. "LCP", "color-contrast", "CVE-2025-1234"
    value: float | None = None
    unit: str | None = None
    evidence: Evidence
    tags: tuple[str, ...] = ()

    @classmethod
    def make(cls, *, product: str, category: Category, title: str, evidence: Evidence,
             **kw) -> "Finding":
        fid = stable_id("F", product, category, evidence.tool, evidence.locator, title)
        return cls(id=fid, product=product, category=category, title=title,
                   evidence=evidence, **kw)


# ----------------------------------------------------------------------------- proposals

# "single_llm": proposals produced by baseline arm A0 (amendment 1, 29 Sep 2026).
Team = Literal["design", "engineering", "product_pricing", "growth", "quality_risk",
               "single_llm"]
Risk = Literal["low", "medium", "high"]


class Proposal(_Frozen):
    """A costed change proposed by one team.

    `areas` is a small controlled vocabulary of what the change touches (e.g.
    "navigation", "signup", "pricing_page"). The Conflict Detector and the Client's
    constraints both work on areas, which is what makes them checkable in code.
    """

    id: str
    team: Team
    title: str
    change: str  # what to do, concretely
    rationale: str  # why, in terms of the cited findings
    finding_ids: tuple[str, ...] = Field(min_length=1)
    cost_days: float = Field(gt=0, le=200)  # engineer-days
    value: int = Field(ge=1, le=10)  # expected impact score, the knapsack objective
    depends_on: tuple[str, ...] = ()  # proposal ids that must ship first
    areas: tuple[str, ...] = Field(min_length=1)
    risk: Risk = "low"
    revision: int = 0

    @field_validator("areas")
    @classmethod
    def _norm_areas(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({a.strip().lower().replace(" ", "_") for a in v if a.strip()}))

    @model_validator(mode="after")
    def _no_self_dependency(self) -> "Proposal":
        if self.id in self.depends_on:
            raise ValueError(f"{self.id} depends on itself")
        return self


# ----------------------------------------------------------------------------- arbitration

ConflictKind = Literal["contradiction", "same_area_overlap", "constraint"]


class Conflict(_Frozen):
    """Two proposals that should not both ship as written.

    `exclusive=True` becomes a hard constraint in the budget solver
    (x_a + x_b <= 1). A non-exclusive conflict is reported but not enforced.
    """

    id: str
    a: str
    b: str
    kind: ConflictKind
    explanation: str
    exclusive: bool = True

    @model_validator(mode="after")
    def _distinct(self) -> "Conflict":
        if self.a == self.b:
            raise ValueError("a conflict needs two different proposals")
        return self


RejectReason = Literal[
    "over_budget", "conflict", "client_veto", "red_team", "unsupported", "dependency"
]


class PlanItem(_Frozen):
    proposal_id: str
    order: int  # 1-based execution wave; items in the same wave can run in parallel
    after: tuple[str, ...] = ()  # proposal ids this item waits for
    cost_days: float
    value: int


class Rejected(_Frozen):
    proposal_id: str
    reason: RejectReason
    detail: str = ""


class Plan(_Frozen):
    id: str
    product: str
    arm: str  # evaluation arm, e.g. "A2"
    round: int = 0  # Client negotiation round that produced this plan
    budget_days: float
    items: tuple[PlanItem, ...]
    rejected: tuple[Rejected, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    total_cost: float
    total_value: int
    notes: str = ""


# ----------------------------------------------------------------------------- client

ReasonCode = Literal["budget", "timeline", "brand", "compliance", "scope", "risk", "other"]


class ClientVerdict(_Frozen):
    """What the team is allowed to see. Deliberately coarse: reason codes and a
    message, never the private constraint text. Inferring the constraint from a
    pattern of these is the information-asymmetry mechanism."""

    plan_id: str
    decision: Literal["accept", "reject"]
    reason_codes: tuple[ReasonCode, ...] = ()
    vetoed_proposal_ids: tuple[str, ...] = ()
    message: str = ""


RuleKind = Literal["forbid_area", "require_area", "max_total_days", "max_risk", "forbid_team"]


class ClientConstraint(_Frozen):
    """A private, machine-checkable client constraint.

    Machine-checkable on purpose: the evaluation counts violations in code, so it
    cannot be argued with by a model. Authored per product BEFORE any run and
    frozen in git (PLAN Section 6, circularity).
    """

    id: str
    product: str
    kind: RuleKind
    param: str  # area name, number, risk level, or team name depending on `kind`
    reason_code: ReasonCode
    description: str  # private, human-readable
    public_hint: str = ""  # what a real client would say if pushed


# ----------------------------------------------------------------------------- runs

class CostLedger(BaseModel):
    """Invariant 9: evidence cost and orchestration cost are separate ledgers."""

    evidence_seconds: float = 0.0  # wall time spent in tool runs
    llm_calls: int = 0
    llm_cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_seconds: float = 0.0  # summed model latency (orchestration cost)


class RunRecord(BaseModel):
    run_id: str
    product: str
    arm: str
    seed: int
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    status: Literal["running", "done", "failed"] = "running"
    plan_id: str | None = None
    client_rounds: int = 0
    red_team_rounds: int = 0
    handoff_rejections: int = 0
    cost: CostLedger = Field(default_factory=CostLedger)
    error: str = ""
    schema_version: str = SCHEMA_VERSION
