"""The reference decision rule and the cost-optimal oracle (PRD S7.5b).

This module is the definition of orchestration quality for the whole project, so
it is deliberately small, pure, and free of I/O. Everything here is a function of
its arguments: no config lookups, no clock, no randomness. That is what makes the
oracle reproducible and hand-checkable.

Read S7.5b before changing anything here. In particular, the oracle is NOT a
lower bound on the system -- it is the cost-optimal plan under a *fixed reference
fusion rule*. Naming that honestly is what removes the circularity that the v1.0
"path selection accuracy" metric had.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

from schemas.evidence import Source

REFERENCE_RULE_VERSION = "logodds-v1"

CONFIDENCE_CLAMP = (0.01, 0.99)
"""Clamp before taking logits.

A detector reporting exactly 0.0 or 1.0 has infinite log-odds and would dominate
every subset it appears in, making the oracle a function of one saturated
detector rather than of the evidence.
"""

DECLARED_COST_MS: dict[Source, int] = {
    Source.TELEMETRY: 50,
    Source.MEMORY: 50,
    Source.VISION: 200,
    Source.AUDIO: 350,
    Source.MANUAL: 400,
}
"""Domain cost per source, in milliseconds. ONE ledger (PRD S5.5b).

These are planning estimates, to be replaced at M2 by measured detector
latencies. The ordering is what matters for oracle selection, and it reflects
real work: a SQLite history lookup is cheap; a mel-spectrogram plus a PaDiM
forward pass is not.

Costed as ACQUISITION ONLY. For memory, this is the SQLite query; for manual, the
retrieval. The LLM reasoning over what either returns is system overhead and is
measured separately, never budgeted.
"""


def clamp_confidence(p: float) -> float:
    lo, hi = CONFIDENCE_CLAMP
    return min(hi, max(lo, p))


def logit(p: float) -> float:
    """Log-odds of a calibrated probability, with clamping applied."""
    q = clamp_confidence(p)
    return math.log(q / (1.0 - q))


def fuse_log_odds(confidences: list[float]) -> float:
    """Sum of log-odds. Bayes-optimal under conditional independence.

    Chosen over mean-of-confidence because the mean is **non-monotone in the
    evidence**: audio 0.95 + vision 0.10 gives a mean of 0.525 (anomalous), and
    adding telemetry 0.15 gives 0.40 (normal). Adding a source would flip a
    correct verdict, which contradicts this project's whole premise that
    gathering more evidence helps. Log-odds pulls the fused value toward zero in
    proportion to a weak source's strength instead of dragging a strong signal
    across the boundary.
    """
    return sum(logit(p) for p in confidences)


def reference_verdict(confidences: list[float]) -> bool:
    """The reference rule's answer: True means anomalous.

    An empty subset returns False: with no evidence at all, log-odds is 0, which
    is exactly the decision boundary. Reading the boundary as "not anomalous"
    means the empty set can never be a sufficient subset for a genuinely
    anomalous incident, which is the behaviour we want.
    """
    return fuse_log_odds(confidences) > 0.0


@dataclass(frozen=True, slots=True)
class OraclePlan:
    """The cost-optimal sufficient subset for one incident, frozen at generation.

    Never recomputed at eval time: changing the fusion rule later would silently
    rewrite every historical results table (PRD S7.5b, same class as R23).
    """

    exists: bool
    sources: tuple[Source, ...]
    cost_ms: int
    rule_version: str = REFERENCE_RULE_VERSION

    @property
    def n_sources(self) -> int:
        return len(self.sources)


def subset_cost_ms(sources: tuple[Source, ...], costs: dict[Source, int] | None = None) -> int:
    table = costs or DECLARED_COST_MS
    return sum(table[s] for s in sources)


def is_sufficient(
    sources: tuple[Source, ...],
    confidences: dict[Source, float],
    is_anomalous: bool,
) -> bool:
    """Would the reference rule, on THIS subset alone, reach the correct verdict?

    Note the asymmetry that makes the empty set behave sensibly: for a normal
    incident the empty set IS sufficient (log-odds 0, verdict normal, correct),
    which is right -- a truly normal machine needs no evidence gathered to be
    correctly left alone. The orchestrator still cannot know that in advance, and
    that unknowability is precisely the "cost of uncertainty" the oracle-to-A1
    gap quantifies.
    """
    if any(s not in confidences for s in sources):
        raise KeyError(f"missing cached confidence for one of {sources}")
    verdict = reference_verdict([confidences[s] for s in sources])
    return verdict == is_anomalous


def compute_oracle(
    confidences: dict[Source, float],
    is_anomalous: bool,
    *,
    costs: dict[Source, int] | None = None,
    allow_empty: bool = False,
) -> OraclePlan:
    """Brute-force the cost-optimal sufficient subset (PRD S7.5b steps 2-5).

    Exhaustive over 2^n subsets, which is 16 for our four queryable sources --
    trivially cheap, and worth preferring over anything clever because it is
    obviously correct and hand-checkable in a viva.

    Selection order: minimum cost_ms, then fewer sources, then lexical source
    order. The last two are tie-breaks purely for determinism; without them the
    oracle could vary between runs on equal-cost subsets and quietly change
    regret numbers.

    `allow_empty=False` by default: the empty set is trivially sufficient for
    every normal incident, and reporting "the optimal plan was to gather nothing"
    for half the eval set would make mean regret meaningless. The orchestrator is
    required to look at least once, so the oracle is held to the same standard.
    """
    table = costs or DECLARED_COST_MS
    available = sorted(confidences.keys(), key=lambda s: s.value)

    best: tuple[Source, ...] | None = None
    best_key: tuple[int, int, tuple[str, ...]] | None = None

    start = 0 if allow_empty else 1
    for size in range(start, len(available) + 1):
        for subset in combinations(available, size):
            if not is_sufficient(subset, confidences, is_anomalous):
                continue
            key = (
                subset_cost_ms(subset, table),
                len(subset),
                tuple(s.value for s in subset),
            )
            if best_key is None or key < best_key:
                best, best_key = subset, key

    if best is None:
        # No subset reaches the right answer. A legitimate, informative outcome:
        # these incidents SHOULD escalate, and they are the ground truth for
        # escalation precision (PRD S12.1).
        return OraclePlan(exists=False, sources=(), cost_ms=0)

    return OraclePlan(exists=True, sources=best, cost_ms=subset_cost_ms(best, table))


def cost_regret(actual_cost_ms: int, oracle: OraclePlan) -> int:
    """How much more the system spent than the oracle would have.

    Non-negative when the system is correct and the oracle exists. Regret against
    this omniscient oracle is NOT achievable by any online policy -- it knows the
    answer and the system does not -- which is why S7.5b requires reporting it
    alongside regret against A1, the achievable baseline.
    """
    return actual_cost_ms - oracle.cost_ms


def source_regret(actual_sources: tuple[Source, ...], oracle: OraclePlan) -> int:
    """Signed difference in number of sources queried.

    Negative means the system gathered LESS than the oracle. Under-gathering is
    weighted harder than over-gathering in the trajectory metric (PRD S12.3),
    because acting on too little evidence is the worse industrial failure.
    """
    return len(actual_sources) - oracle.n_sources
