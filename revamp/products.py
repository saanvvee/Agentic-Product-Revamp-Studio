"""Product configuration: everything product-specific lives in products/<name>.yaml.

The code is product-agnostic (PLAN D2). Adding a product means writing one YAML file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from revamp.settings import settings


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Live(_M):
    base_url: str
    pages: list[str] = Field(min_length=1)  # paths audited with PSI/axe/SEO
    pricing_url: str | None = None
    competitor_pricing: dict[str, str] = {}


class Forum(_M):
    kind: str = "discourse"
    base_url: str


class Flow(_M):
    """A scripted user journey for Playwright: visit steps in order, screenshot each."""
    name: str
    steps: list[str]  # paths relative to the audit target's base URL


class AnswerKey(_M):
    """The redesign the product really shipped after `old_ref` (PLAN F3)."""
    old_ref: str
    new_ref: str
    shipped_on: date
    themes: list[str] = []  # written by hand BEFORE any run, blind to outputs
    sources: list[str] = []


class Product(_M):
    name: str
    repo: str  # owner/name on GitHub
    extra_repos: list[str] = []  # e.g. a separate frontend repo
    ref: str  # git ref audited for code/security; the old release if answer_key is set
    cutoff: date  # Voice of Customer only sees items created before this (invariant 7)
    budget_days: float  # engineering capacity for the revamp plan
    live: Live
    local_base_url: str | None = None  # a local Docker instance, if running
    forum: Forum | None = None
    flows: list[Flow] = []
    answer_key: AnswerKey | None = None
    notes: str = ""


def load_product(name: str, directory: Path | None = None) -> Product:
    path = (directory or settings.products_dir) / f"{name}.yaml"
    return Product.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_products(directory: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (directory or settings.products_dir).glob("*.yaml"))


def load_constraints(name: str, directory: Path | None = None):
    """Private client constraints for a product, from products/constraints/<name>.yaml.

    These files are the evaluation's hidden ground truth. They must be written
    BEFORE any evaluation run, by someone who did not write the agent prompts, and
    committed so their timestamp shows it (PLAN Section 6, circularity).
    """
    from revamp.contracts import ClientConstraint
    path = (directory or settings.products_dir) / "constraints" / f"{name}.yaml"
    if not path.is_file():
        return []
    rows = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [ClientConstraint(product=name, **r) for r in rows]
