"""Domain-cost budget accounting (PRD S5.5a, S5.5b).

This is the mechanism the whole project rests on, so it is pure: no I/O, no
clock, no LLM, no config lookup. A ledger is constructed with its limits and then
only ever told about costs. Everything about why the system stopped is derivable
from the ledger afterwards.

FOUR DECISIONS the PRD did not answer, resolved here and documented at the point
of enforcement:

  1. Admission rejection with budget remaining is NOT budget exhaustion. It gets
     its own terminal state, NO_AFFORDABLE_SOURCE, because the decision log's
     whole purpose is explaining why the system stopped.
  2. A rejected admission CONSUMES an evidence step. Planning is not free, and it
     makes termination fall out of the existing bound instead of needing a new
     counter.
  3. Parallel group admission is ALL-OR-NOTHING, and availability is logged
     separately from choice -- otherwise "prefers sequential under pressure" reads
     as orchestrator behaviour when it is an admission-control artifact.
  4. The fast path draws from the SAME budget, with no exception. Its cheapness
     must be an emergent property of querying one source, not a special case in
     the accounting, or cross-path cost comparisons measure different things.

WHAT IS BUDGETED: domain cost only -- modelled sensor acquisition plus detector
inference, in milliseconds. LLM latency and tokens are system overhead: measured,
reported, never debited (PRD S5.5b).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from schemas.evidence import Source


class TerminalReason(str, Enum):
    """Why an incident stopped consuming evidence.

    Recorded in decisions.jsonl for every incident. These are deliberately
    distinct: collapsing any two would make the log unable to answer the one
    question it exists to answer.
    """

    RESOLVED = "resolved"
    """The critic accepted the evidence."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    """Spend reached the limit. Nothing further could be afforded at any price."""

    NO_AFFORDABLE_SOURCE = "no_affordable_source"
    """Budget REMAINS, but every ungathered source costs more than what is left.

    Decision 1. Distinct from exhaustion: the system stopped with money in hand
    because nothing on the shelf was cheap enough. Reporting this as exhaustion
    would misstate the mechanism -- the fix for one is a bigger budget, for the
    other a cheaper source.
    """

    STEPS_EXHAUSTED = "steps_exhausted"
    """Hit max_evidence_steps (PRD S5.6). Bounded independently of cost so a
    pathological plan cannot loop even when every source is cheap."""

    ESCALATED = "escalated"
    """Handed to a human. The correct outcome on an unresolvable incident."""


class AdmissionOutcome(str, Enum):
    ADMITTED = "admitted"
    REJECTED_COST = "rejected_cost"
    REJECTED_STEPS = "rejected_steps"
    REJECTED_ALREADY_GATHERED = "rejected_already_gathered"
    """PRD S11.3: the critic may not re-request a source already gathered."""


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """The result of asking to spend. Immutable, and logged verbatim."""

    outcome: AdmissionOutcome
    sources: tuple[Source, ...]
    declared_cost_ms: int
    remaining_before_ms: int
    reason: str

    @property
    def admitted(self) -> bool:
        return self.outcome is AdmissionOutcome.ADMITTED


@dataclass(frozen=True, slots=True)
class Debit:
    """One recorded spend, at measured cost."""

    sources: tuple[Source, ...]
    declared_cost_ms: int
    measured_cost_ms: int
    parallel: bool

    @property
    def drift_ms(self) -> int:
        """Measured minus declared.

        Published as a free result (PRD S5.5a): declared cost is a model
        parameter and measured cost is an observation, so their drift says how
        good the model is. It is NOT an error term.
        """
        return self.measured_cost_ms - self.declared_cost_ms


class BudgetLedger:
    """Two ledgers that compose differently, and admission control over both.

    Latency takes the MAX within a parallel group and the SUM across sequential
    steps, because wall-clock is what a plant supervisor waits for. Tokens always
    sum, because every token is billed whether or not calls overlapped -- but
    tokens are tracked for reporting only and never gate admission (PRD S5.5b).
    """

    def __init__(
        self,
        *,
        budget_ms: int,
        budget_tokens: int,
        max_evidence_steps: int,
        declared_costs: dict[Source, int],
    ) -> None:
        if budget_ms <= 0:
            raise ValueError("budget_ms must be positive")
        self._budget_ms = budget_ms
        self._budget_tokens = budget_tokens
        self._max_steps = max_evidence_steps
        self._declared = dict(declared_costs)

        self._spent_ms = 0
        self._spent_tokens = 0
        self._steps_used = 0
        self._gathered: list[Source] = []
        self._debits: list[Debit] = []
        self._admissions: list[AdmissionDecision] = []

    # -- state ------------------------------------------------------------

    @property
    def budget_ms(self) -> int:
        return self._budget_ms

    @property
    def spent_ms(self) -> int:
        return self._spent_ms

    @property
    def remaining_ms(self) -> int:
        """Never negative. Overspend is bounded by one group's drift (see
        `record`), and a negative balance would make the log harder to read for
        no gain."""
        return max(0, self._budget_ms - self._spent_ms)

    @property
    def spent_tokens(self) -> int:
        return self._spent_tokens

    @property
    def steps_used(self) -> int:
        return self._steps_used

    @property
    def steps_remaining(self) -> int:
        return max(0, self._max_steps - self._steps_used)

    @property
    def gathered(self) -> tuple[Source, ...]:
        return tuple(self._gathered)

    @property
    def debits(self) -> tuple[Debit, ...]:
        return tuple(self._debits)

    @property
    def admissions(self) -> tuple[AdmissionDecision, ...]:
        """Every admission request, including rejections.

        Rejections are the interesting half: they are what distinguishes "chose
        not to" from "could not" when the results are read.
        """
        return tuple(self._admissions)

    # -- planning ---------------------------------------------------------

    def declared_cost(self, sources: tuple[Source, ...], *, parallel: bool) -> int:
        """Planning cost of a group, under the composition rule for its shape.

        Decision 4: the fast path is just `sources` of length one. There is no
        separate accounting for it, so its cheapness is emergent rather than
        privileged, and a fast-path cost is directly comparable to a parallel
        one.
        """
        if not sources:
            return 0
        costs = [self._declared[s] for s in sources]
        return max(costs) if parallel else sum(costs)

    def can_afford(self, sources: tuple[Source, ...], *, parallel: bool) -> bool:
        """Pure query: would this group be admitted on cost alone?

        Used to log parallel AVAILABILITY at every path decision (decision 3)
        without consuming a step. Availability and choice must be separable in
        the data or "prefers sequential under pressure" is uninterpretable.
        """
        return self.declared_cost(sources, parallel=parallel) <= self.remaining_ms

    def affordable_sources(self, candidates: tuple[Source, ...]) -> tuple[Source, ...]:
        """Which ungathered candidates could still be admitted individually.

        Empty means NO_AFFORDABLE_SOURCE is the correct terminal state, and it is
        how that condition is detected rather than inferred.
        """
        return tuple(
            s
            for s in candidates
            if s not in self._gathered and self._declared[s] <= self.remaining_ms
        )

    # -- admission --------------------------------------------------------

    def request(
        self, sources: tuple[Source, ...], *, parallel: bool = False
    ) -> AdmissionDecision:
        """Ask to spend. Records the decision either way.

        ADMISSION CONTROL, NOT INTERRUPTION (PRD S5.5a): a group is admitted only
        if its DECLARED cost fits what remains, and an in-flight call is never
        killed. Consequence, which the report states as a bound: total spend can
        exceed the budget by at most one group's declared-to-measured drift, and
        never more.

        Decision 2: a rejection consumes an evidence step, exactly like an
        admission. Planning is not free, and it means a system that keeps
        proposing unaffordable groups terminates on STEPS_EXHAUSTED instead of
        spinning.

        Decision 3: parallel admission is all-or-nothing. A group that does not
        fit is rejected whole; the caller may re-plan a smaller group, which
        costs another step.
        """
        remaining = self.remaining_ms
        declared = self.declared_cost(sources, parallel=parallel)

        already = [s for s in sources if s in self._gathered]
        if already:
            # Checked before the step is consumed: re-requesting a gathered
            # source is a logic error in the critic, not a budget event, and
            # charging a step for it would hide the bug (PRD S11.3).
            decision = AdmissionDecision(
                outcome=AdmissionOutcome.REJECTED_ALREADY_GATHERED,
                sources=sources,
                declared_cost_ms=declared,
                remaining_before_ms=remaining,
                reason=(
                    f"already gathered: {[s.value for s in already]}; the critic "
                    "may not re-request a source (PRD S11.3)"
                ),
            )
            self._admissions.append(decision)
            return decision

        if self.steps_remaining <= 0:
            decision = AdmissionDecision(
                outcome=AdmissionOutcome.REJECTED_STEPS,
                sources=sources,
                declared_cost_ms=declared,
                remaining_before_ms=remaining,
                reason=f"evidence step cap reached ({self._max_steps})",
            )
            self._admissions.append(decision)
            return decision

        if declared > remaining:
            self._steps_used += 1  # decision 2: rejection costs a step
            shape = "parallel group" if parallel else "sequential step"
            decision = AdmissionDecision(
                outcome=AdmissionOutcome.REJECTED_COST,
                sources=sources,
                declared_cost_ms=declared,
                remaining_before_ms=remaining,
                reason=(
                    f"{shape} declares {declared} ms but only {remaining} ms "
                    f"remains; admitted all-or-nothing"
                ),
            )
            self._admissions.append(decision)
            return decision

        self._steps_used += 1
        decision = AdmissionDecision(
            outcome=AdmissionOutcome.ADMITTED,
            sources=sources,
            declared_cost_ms=declared,
            remaining_before_ms=remaining,
            reason=f"declares {declared} ms against {remaining} ms remaining",
        )
        self._admissions.append(decision)
        return decision

    def record(
        self,
        sources: tuple[Source, ...],
        *,
        measured_cost_ms: int,
        measured_tokens: int = 0,
        parallel: bool = False,
    ) -> Debit:
        """Debit the MEASURED cost after a group has run.

        Separate from `request` on purpose: the orchestrator plans against
        declared cost and the ledger debits what actually happened, so the drift
        between them is observable instead of assumed away.
        """
        if measured_cost_ms < 0:
            raise ValueError("measured_cost_ms cannot be negative")

        debit = Debit(
            sources=sources,
            declared_cost_ms=self.declared_cost(sources, parallel=parallel),
            measured_cost_ms=measured_cost_ms,
            parallel=parallel,
        )
        self._spent_ms += measured_cost_ms
        self._spent_tokens += measured_tokens
        self._gathered.extend(sources)
        self._debits.append(debit)
        return debit

    # -- termination ------------------------------------------------------

    def terminal_reason(
        self, candidates: tuple[Source, ...], *, resolved: bool
    ) -> TerminalReason:
        """Why this incident stopped. Checked in priority order.

        RESOLVED wins over everything: reaching an answer on the last affordable
        source is a success, not an exhaustion. Then the three distinct ways of
        running out, which the log must keep apart.
        """
        if resolved:
            return TerminalReason.RESOLVED
        if self.steps_remaining <= 0:
            return TerminalReason.STEPS_EXHAUSTED
        if self.remaining_ms <= 0:
            return TerminalReason.BUDGET_EXHAUSTED
        if not self.affordable_sources(candidates):
            # Budget remains but nothing fits: decision 1.
            return TerminalReason.NO_AFFORDABLE_SOURCE
        return TerminalReason.ESCALATED

    def snapshot(self) -> dict[str, object]:
        """Everything decisions.jsonl needs for one incident (PRD S5.5a).

        Includes rejection counts so that, at analysis time, "chose not to" and
        "could not" remain distinguishable without re-running anything.
        """
        return {
            "budget_ms": self._budget_ms,
            "spent_ms": self._spent_ms,
            "remaining_ms": self.remaining_ms,
            "spent_tokens": self._spent_tokens,
            "steps_used": self._steps_used,
            "steps_remaining": self.steps_remaining,
            "gathered": [s.value for s in self._gathered],
            "declared_total_ms": sum(d.declared_cost_ms for d in self._debits),
            "drift_ms": sum(d.drift_ms for d in self._debits),
            "n_rejected_cost": sum(
                1
                for a in self._admissions
                if a.outcome is AdmissionOutcome.REJECTED_COST
            ),
            "n_admissions": len(self._admissions),
        }


@dataclass(frozen=True, slots=True)
class PathAvailability:
    """Which paths admission control permits at one decision point (decision 3).

    Logged at EVERY path decision, separately from what was chosen. Without this,
    "the orchestrator prefers sequential under budget pressure" is unfalsifiable:
    it could be policy or it could be that parallel was never on the menu. With
    it, two rates are reportable --

        parallel chosen when available    -> orchestrator BEHAVIOUR
        parallel unavailable by admission -> MECHANISM

    and a large second number is itself a finding worth a paragraph: under budget
    pressure the design structurally forces sequential investigation.
    """

    fast_available: bool
    parallel_available: bool
    sequential_available: bool
    remaining_ms: int
    parallel_declared_ms: int

    def as_log_fields(self) -> dict[str, object]:
        return {
            "fast_available": self.fast_available,
            "parallel_available": self.parallel_available,
            "sequential_available": self.sequential_available,
            "remaining_ms_at_decision": self.remaining_ms,
            "parallel_declared_ms": self.parallel_declared_ms,
        }


def assess_paths(
    ledger: BudgetLedger, candidates: tuple[Source, ...]
) -> PathAvailability:
    """What could be afforded right now, without consuming a step."""
    ungathered = tuple(s for s in candidates if s not in ledger.gathered)
    return PathAvailability(
        fast_available=bool(ledger.affordable_sources(candidates)),
        parallel_available=bool(ungathered)
        and ledger.can_afford(ungathered, parallel=True),
        sequential_available=bool(ledger.affordable_sources(candidates)),
        remaining_ms=ledger.remaining_ms,
        parallel_declared_ms=ledger.declared_cost(ungathered, parallel=True),
    )
