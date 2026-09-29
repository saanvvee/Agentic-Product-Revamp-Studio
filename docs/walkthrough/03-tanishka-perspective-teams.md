# Walkthrough 03: user perspective, vision, proposal teams (owner: Tanishka)

Files: `revamp/agents/perspective.py`, `revamp/agents/teams.py`, `revamp/tools/browser.py`,
`revamp/tools/voice.py`, and in `revamp/workflow/nodes.py` the functions `perspectives`,
`propose`, `handoff` and `drafts_to_proposals`.

## Voice of Customer

- **Input:** up to 40 real posts (GitHub issues, Discourse topics), each with an engagement
  score. All were created before the product's cutoff.
- **Output:** themes, each marked signal or noise and citing post ids. A theme that cites no real
  post is dropped in code.
- **Only signal themes reach the teams.** Noise includes installation help for one environment,
  one-off bugs and spam. The judgment is the agent's reason to exist.

## Journey Auditor (second modality)

- `tools/browser.py::run_journey` walks each scripted flow (`products/<name>.yaml → flows`),
  screenshots every step, and records HTTP errors, console errors, failed requests and load
  time.
- The agent receives the screenshots as inline image parts (Gemini vision) plus the step facts.
- Every issue it reports must name the finding id of a real step. Code turns each issue into a
  `Finding` whose evidence is that screenshot (`tool="journey_auditor_vision"`, tag
  `llm_observation`). So even the model's observations cite an artifact.
- On the local model (no vision) it gets the step facts only. The report should say which mode
  a run used.

## Proposal teams

- Design, Engineering and Product & Pricing see the same evidence, the engagement focus, the
  signal themes and the journey issues. They do not see each other while proposing. That is
  deliberate: contradictions between teams are what arbitration exists to catch.
- **Drafts become `Proposal`s in `drafts_to_proposals`:**
  - Ids are assigned by code (`DE1-2` = Design, proposing round 1, item 2).
  - Unknown finding ids are removed, and a draft left with none is dropped.
  - Both events are counted (`citations_invalid`, `unsupported_dropped`). This is the
    hallucination metric in the evaluation.
- **Costing:** the team prompt gives cost anchors (a copy fix is 0.5–1 day, a page redesign
  5–15). Engineering's handoff review can reject a cost as unrealistic.

## Handoff rejection (the backward edge)

- Engineering reviews the other teams' proposals once each.
- A rejection sends feedback to the proposing team and routes back to `propose` for that team
  only, at most `HANDOFF_CAP` times.
- After the cap, Engineering's cost estimate replaces the proposer's (the revision is bumped and
  stored).

## Viva questions

1. A Voice of Customer theme cites a post id the model invented. What happens to it, and where
   in the code?
2. Why do teams not see each other's proposals while proposing?
3. The Journey Auditor is an LLM. How can its output count as evidence?
4. What does the id `PP2-1` tell you?
5. Why does the complaint cutoff matter for the answer-key evaluation?
