# Walkthrough 02: orchestration and arbitration (owner: Saksham)

Files: `revamp/workflow/{graph,nodes,arms,run_context,runner,prompts}.py`,
`revamp/arbitration/{budget,sequencer,plan,constraints}.py`, `revamp/agents/arbitration.py`.

## The graph (`workflow/graph.py`)

ADK 2.9: `Workflow(edges=[...])`. A tuple is a chain of nodes; a dict is a routing map keyed by
the value a node puts in `ctx.route`.

```
START → init → brief → perspectives → propose → handoff
handoff   revise→propose | ok→conflicts → allocate → red_team
red_team  replan→allocate | ok→client
client    accept→approve | reject→adapt | stop→finalize
approve   ok→finalize | replan→allocate
adapt     replan→allocate | propose→propose
```

- **ADK only accepts a cycle if it passes through a routed edge.** An unconditional cycle is
  rejected when the graph is built.
- **ADK does not bound cycles.** The caps are in `arms.py` (`HANDOFF_CAP=2`, `RED_TEAM_CAP=2`,
  `CLIENT_CAP=3`) and are checked in the nodes before routing back.
- **One edge per node pair.** Two labels pointing at the same target is a "duplicate edge"
  error. That is why A0 uses `DEFAULT_ROUTE`.

## Nodes (`workflow/nodes.py`)

- **Session state holds only plain values:** ids, counters, the budget, and the blocked map.
  Everything else hangs off a `RunContext` looked up by `run_id`: KB handles, agents, proposals,
  the current plan, and the cost record.
- **Each agent runs in a fresh, short session** through `agents/runtime.py::ask`, and sees only
  the prompt its node built (`workflow/prompts.py`).
- **Parallelism:** `perspectives` runs Voice of Customer and Journey Auditor with
  `asyncio.gather`, and `propose` runs the three teams the same way. The semaphore in
  `CachedLlm` keeps it to 3 LLM calls in flight.
- **The `approve` node must not set `ctx.route` before pausing.** ADK records a route set before
  an interrupt, and on resume it fast-forwards past the node using that route. We hit this bug,
  then read `_replay_interceptor.py` ("Case 4") to understand it.

## Arms (`workflow/arms.py`)

Every arm except A0 uses the same graph. Each ablation turns one switch off inside the nodes,
so a difference between A2 and an ablation is caused by that one mechanism.

## Budget Allocator (`arbitration/budget.py`)

A 0/1 knapsack with precedence and conflict constraints, solved exactly with
`scipy.optimize.milp`:

```
maximise   Σ value_i x_i
subject to Σ cost_i x_i ≤ budget
           x_i ≤ x_j            (i depends on j)
           x_a + x_b ≤ 1        (exclusive conflict)
           x_i = 0              (blocked: veto, red team, dependency)
```

- **Why not greedy:** see `test_two_cheap_beat_one_expensive` and
  `test_precedence_cheap_enabler_unlocks_value`. Greedy fails exactly the cases the synopsis
  cares about.
- **Ties:** a tiny cost term breaks them towards the cheaper plan, so the result is
  deterministic.
- **Transitive blocking:** a missing dependency blocks the item that needs it, and anything that
  in turn needs that item.

## Dependency Sequencer (`arbitration/sequencer.py`)

Kahn's algorithm, layered into waves. A cycle is an error, and `nodes._break_cycles` blocks one
member of any cycle before solving.

## Conflict Detector and Red Team (`agents/arbitration.py`)

LLM judgments a solver cannot make:
- A conflict marked **exclusive** becomes an ILP constraint.
- A red-team **block** becomes a blocked item followed by a re-solve. A **flag** is only counted.

## Viva questions

1. Write the ILP on the board. Why is `x_i ≤ x_j` the right precedence constraint?
2. Give three proposals where greedy by value/cost picks a worse plan than the ILP.
3. Where exactly is the client loop bounded? What happens on the 4th rejection?
4. Why does `approve` set `ctx.route` only after it has the human's answer?
5. Why does every arm except A0 share one graph? What would break if A3 used a different graph?
