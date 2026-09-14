# Design journal — member-a

Three lines after every work session: what changed, why, what next.

Two minutes a day. This is the difference between a confident viva and a
stumbling one, and it is the contemporaneous record of our own reasoning
(PRD S17.2, R16).

---

## 2026-09-14

- **Changed:** Budget accounting, memory store seam, constructed demo split,
  verdict-to-tier mapping. Recalibrated budget tiers (900/600/250 ms), incident
  spacing (1h -> 6h), memory rule windows.
- **Why:** Five times now, a mechanism has passed every test while being unable
  to discriminate: budget tiers, memory windows, Tier 3 rate, the false-alarm
  base rate, the lower_threshold overlap. Only arithmetic against measured data
  caught any of them. **The degenerate direction (~100%) is more dangerous than
  the inert one (~0%), because it yields a confident number instead of an empty
  one.** An inert mechanism produces a suspiciously empty result I would have
  chased eventually. A memory rule firing on 86.7% of incidents produces a clean
  A3 null result that I would have written up and defended.
- **Next:** Guardrails (tier logic, five work-order templates, Tier 3 blocking).
  Then triage, orchestrator, critic -- the agents themselves.

## 2026-09-13

- **Changed:** [fill in]
- **Why:** [fill in]
- **Next:** [fill in]
