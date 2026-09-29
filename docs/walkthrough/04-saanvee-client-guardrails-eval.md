# Walkthrough 04: Client over A2A, guardrails, evaluation (owner: Saanvee)

Files: `revamp/client_service.py`, `revamp/agents/client.py`,
`revamp/arbitration/constraints.py`, `revamp/workflow/nodes.py` (`client`, `adapt`, `approve`),
`revamp/evaluation.py`, `revamp/report.py`, `products/constraints/`.

## The Client

- **Private constraints** live in `products/constraints/<product>.yaml` and are loaded into the
  KB's `client_private` namespace by `revamp constraints <product>`. They are machine-checkable
  rules: `forbid_area`, `require_area`, `max_total_days`, `max_risk`, `forbid_team`.
- **The decision is code:** `arbitration/constraints.py::check` (see `client_service.evaluate`).
  The LLM only writes the message, from each violated constraint's public hint. It never sees
  the private description.
- **Why rule-based:**
  - The veto is exact.
  - The evaluation metric (hidden-constraint violations) runs the same `check` function, so
    behaviour and measurement cannot drift apart.
- **Veto, not vote.** A rejection is binding. It is not averaged with the teams' views. After a
  rejection the Engagement Lead must infer the constraint from the reason codes and adapt:
  - drop items;
  - lower the budget;
  - ask a team to cover a missing area.
- **Loop cap:** `CLIENT_CAP = 3`.

## A2A process boundary

- `python -m revamp.client_service --port 8765` serves the Client as an ADK `Workflow` through
  `to_a2a`.
- With `REVAMP_CLIENT_URL` set, the orchestrator calls it through `RemoteA2aAgent` and never
  opens the client namespace.
- The asymmetry is enforced twice: by a process boundary and by the KB role.
- Use `localhost`, not `127.0.0.1`: the A2A card origin is enforced.
- Tested over real HTTP in `tests/test_client_a2a.py`.

## Human-in-the-loop guardrail

- `approve` pauses the run with `RequestInput` when the plan contains high-impact items (high
  risk, or cost ≥ 25% of the budget).
- The runner asks a human (the `--hitl` terminal prompt) and resumes the same session with a
  `FunctionResponse`.
- Rejected items are blocked and the plan is re-solved. The human is asked at most once per run.

## Evaluation (`evaluation.py`)

- **Arms A0–A6** (`workflow/arms.py`).
- **Metrics are computed in code from the KB**, with the evaluator role, because they read the
  hidden constraints:

| Metric | Meaning |
|---|---|
| `hidden_violations` | Plan items breaking private constraints |
| `over_budget_days` | Against the product's original budget |
| `dependency_violations` | A dependency missing, or not scheduled earlier |
| `cross_team_overlaps` | Different teams touching the same area (a crude contradiction proxy) |
| `citation_invalid_rate` | Share of cited ids that did not exist (hallucination) |
| `client_rounds`, `client_accepted` | How the negotiation went |
| `answer_key_recall` | Share of shipped redesign themes the plan touches (descriptive only) |
| Evidence seconds vs LLM calls/tokens/seconds | Reported separately |

**Circularity rules:**
1. Constraints are written before any run, by someone who did not write the prompts, and
   committed.
2. Answer-key themes are written blind to outputs.
3. Voice of Customer and CVE data stop at the cutoff.

## Viva questions

1. Why is the Client's decision code and not the LLM's judgment? What would we lose, and what
   would we gain, if it were an LLM?
2. How does the team learn about a constraint it cannot read?
3. Why must metrics use the evaluator role? What would a metric computed with the team role
   miss?
4. What does A6 measure, and why is a small gap between A2 and A6 a good result?
5. Why is answer-key recall "descriptive, never the only score"?
