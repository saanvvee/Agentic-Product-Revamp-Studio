"""Knowledge base: SQLite with namespaces enforced in code (PLAN M2, invariant 3).

Why enforcement lives here and not in a prompt: ADK session state is one shared
dict with no access control (verified in ADK 2.9 source). If the Client's private
constraints were in state or in a prompt, any team agent could read them. So the
only door to the private data is this class, and the door checks the caller's role.

Namespaces and who may touch them:

    namespace        read                      write
    shared           team, client, evaluator   team, evaluator
    client_private   client, evaluator         client, evaluator
    priors           team, evaluator           evaluator (Retro)

A KnowledgeBase object is opened FOR a role. The MCP server opens one per caller
role; agents never get a handle with a wider role than their own.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Literal

from revamp.contracts import (
    ClientConstraint,
    ClientVerdict,
    Finding,
    Plan,
    Proposal,
    RunRecord,
)

Role = Literal["team", "client", "evaluator"]
Namespace = Literal["shared", "client_private", "priors"]

_READ: dict[Namespace, set[str]] = {
    "shared": {"team", "client", "evaluator"},
    "client_private": {"client", "evaluator"},
    "priors": {"team", "evaluator"},
}
_WRITE: dict[Namespace, set[str]] = {
    "shared": {"team", "evaluator"},
    "client_private": {"client", "evaluator"},
    "priors": {"evaluator"},
}


class AccessDenied(PermissionError):
    pass


class ProvenanceError(ValueError):
    """A proposal cites a finding that does not exist (invariant 2)."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY, product TEXT NOT NULL, category TEXT NOT NULL,
    severity TEXT NOT NULL, observed_at TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals (
    run_id TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
    team TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY (run_id, id, revision));
CREATE TABLE IF NOT EXISTS provenance (
    run_id TEXT NOT NULL, proposal_id TEXT NOT NULL, finding_id TEXT NOT NULL,
    PRIMARY KEY (run_id, proposal_id, finding_id));
CREATE TABLE IF NOT EXISTS plans (
    run_id TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
    PRIMARY KEY (run_id, id));
CREATE TABLE IF NOT EXISTS verdicts (
    run_id TEXT NOT NULL, plan_id TEXT NOT NULL, body TEXT NOT NULL,
    PRIMARY KEY (run_id, plan_id));
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, body TEXT NOT NULL);
-- client_private
CREATE TABLE IF NOT EXISTS client_constraints (
    id TEXT PRIMARY KEY, product TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS client_log (
    run_id TEXT NOT NULL, plan_id TEXT NOT NULL, body TEXT NOT NULL);
-- priors
CREATE TABLE IF NOT EXISTS priors (
    key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class KnowledgeBase:
    def __init__(self, path: Path | str, role: Role):
        if role not in {"team", "client", "evaluator"}:
            raise ValueError(f"unknown role {role!r}")
        self.role: Role = role
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection per KB object; a lock because the MCP server and ADK run
        # tool calls from several asyncio tasks that may land on worker threads.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    @classmethod
    def sibling(cls, other: "KnowledgeBase", role: Role) -> "KnowledgeBase":
        """Open the same database file for a different role (tests, orchestrator)."""
        return cls(other.path, role)

    def close(self) -> None:
        self._conn.close()

    # --------------------------------------------------------------- access control

    def _check(self, ns: Namespace, op: Literal["read", "write"]) -> None:
        allowed = _READ[ns] if op == "read" else _WRITE[ns]
        if self.role not in allowed:
            raise AccessDenied(f"role {self.role!r} may not {op} namespace {ns!r}")

    def _rows(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self._lock:
            return self._conn.execute(sql, args).fetchall()

    def _write(self, sql: str, args: tuple = ()) -> None:
        with self._lock, self._conn:
            self._conn.execute(sql, args)

    # --------------------------------------------------------------- shared: findings

    def add_findings(self, findings: list[Finding]) -> int:
        """Upsert by id. Returns how many were new."""
        self._check("shared", "write")
        new = 0
        with self._lock, self._conn:
            for f in findings:
                exists = self._conn.execute(
                    "SELECT 1 FROM findings WHERE id=?", (f.id,)).fetchone()
                new += exists is None
                self._conn.execute(
                    "INSERT OR REPLACE INTO findings VALUES (?,?,?,?,?,?)",
                    (f.id, f.product, f.category, f.severity,
                     f.evidence.observed_at.isoformat(), f.model_dump_json()))
        return new

    def findings(self, product: str, category: str | None = None,
                 min_severity: str | None = None) -> list[Finding]:
        self._check("shared", "read")
        sql, args = "SELECT body FROM findings WHERE product=?", [product]
        if category:
            sql += " AND category=?"
            args.append(category)
        out = [Finding.model_validate_json(r[0]) for r in self._rows(sql, tuple(args))]
        if min_severity:
            from revamp.contracts import SEVERITY_RANK
            floor = SEVERITY_RANK[min_severity]
            out = [f for f in out if SEVERITY_RANK[f.severity] >= floor]
        return sorted(out, key=lambda f: f.id)

    def finding_ids(self, product: str) -> set[str]:
        self._check("shared", "read")
        return {r[0] for r in self._rows("SELECT id FROM findings WHERE product=?", (product,))}

    # --------------------------------------------------------------- shared: proposals

    def add_proposal(self, run_id: str, product: str, p: Proposal) -> None:
        """Rejects any proposal citing a finding the KB does not hold (invariant 2)."""
        self._check("shared", "write")
        known = self.finding_ids(product)
        missing = [fid for fid in p.finding_ids if fid not in known]
        if missing:
            raise ProvenanceError(f"{p.id} cites unknown findings {missing}")
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO proposals VALUES (?,?,?,?,?)",
                               (run_id, p.id, p.revision, p.team, p.model_dump_json()))
            for fid in p.finding_ids:
                self._conn.execute("INSERT OR IGNORE INTO provenance VALUES (?,?,?)",
                                   (run_id, p.id, fid))

    def proposals(self, run_id: str, latest_only: bool = True) -> list[Proposal]:
        self._check("shared", "read")
        rows = self._rows("SELECT id, revision, body FROM proposals WHERE run_id=?"
                          " ORDER BY id, revision", (run_id,))
        if not latest_only:
            return [Proposal.model_validate_json(b) for _, _, b in rows]
        latest: dict[str, str] = {}
        for pid, _, body in rows:
            latest[pid] = body  # rows are ordered by revision, so the last wins
        return [Proposal.model_validate_json(b) for b in latest.values()]

    def evidence_chain(self, run_id: str, proposal_id: str) -> list[Finding]:
        self._check("shared", "read")
        rows = self._rows(
            "SELECT f.body FROM provenance p JOIN findings f ON f.id=p.finding_id"
            " WHERE p.run_id=? AND p.proposal_id=?", (run_id, proposal_id))
        return [Finding.model_validate_json(r[0]) for r in rows]

    # --------------------------------------------------------------- shared: plans, runs

    def add_plan(self, run_id: str, plan: Plan) -> None:
        self._check("shared", "write")
        self._write("INSERT OR REPLACE INTO plans VALUES (?,?,?)",
                    (run_id, plan.id, plan.model_dump_json()))

    def plans(self, run_id: str) -> list[Plan]:
        self._check("shared", "read")
        return [Plan.model_validate_json(r[0])
                for r in self._rows("SELECT body FROM plans WHERE run_id=?", (run_id,))]

    def add_verdict(self, run_id: str, v: ClientVerdict) -> None:
        # The public verdict is shared: the team must see it to adapt. The client
        # writes it, so this one write path is open to the client role too.
        if self.role not in {"client", "evaluator"}:
            raise AccessDenied("only the client records verdicts")
        self._write("INSERT OR REPLACE INTO verdicts VALUES (?,?,?)",
                    (run_id, v.plan_id, v.model_dump_json()))

    def verdicts(self, run_id: str) -> list[ClientVerdict]:
        self._check("shared", "read")
        return [ClientVerdict.model_validate_json(r[0]) for r in
                self._rows("SELECT body FROM verdicts WHERE run_id=? ORDER BY rowid", (run_id,))]

    def save_run(self, rec: RunRecord) -> None:
        self._check("shared", "write")
        self._write("INSERT OR REPLACE INTO runs VALUES (?,?)", (rec.run_id, rec.model_dump_json()))

    def run(self, run_id: str) -> RunRecord | None:
        self._check("shared", "read")
        rows = self._rows("SELECT body FROM runs WHERE run_id=?", (run_id,))
        return RunRecord.model_validate_json(rows[0][0]) if rows else None

    # --------------------------------------------------------------- client_private

    def set_constraints(self, product: str, constraints: list[ClientConstraint]) -> None:
        self._check("client_private", "write")
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM client_constraints WHERE product=?", (product,))
            for c in constraints:
                self._conn.execute("INSERT INTO client_constraints VALUES (?,?,?)",
                                   (c.id, product, c.model_dump_json()))

    def constraints(self, product: str) -> list[ClientConstraint]:
        self._check("client_private", "read")
        return [ClientConstraint.model_validate_json(r[0]) for r in
                self._rows("SELECT body FROM client_constraints WHERE product=?", (product,))]

    def log_private(self, run_id: str, plan_id: str, note: dict) -> None:
        self._check("client_private", "write")
        self._write("INSERT INTO client_log VALUES (?,?,?)", (run_id, plan_id, json.dumps(note)))

    def private_log(self, run_id: str) -> list[dict]:
        self._check("client_private", "read")
        return [json.loads(r[0]) for r in
                self._rows("SELECT body FROM client_log WHERE run_id=?", (run_id,))]

    # --------------------------------------------------------------- priors

    def prior(self, key: str, default=None):
        self._check("priors", "read")
        rows = self._rows("SELECT value FROM priors WHERE key=?", (key,))
        return json.loads(rows[0][0]) if rows else default

    def set_prior(self, key: str, value) -> None:
        self._check("priors", "write")
        self._write("INSERT OR REPLACE INTO priors VALUES (?,?)", (key, json.dumps(value)))
