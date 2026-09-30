"""`python -m revamp doctor`: is this machine ready to run the studio?

Checks, in order: Python, .env keys, Ollama reachable, the three model tags pulled,
each model actually loaded ON THE GPU (Ollama's /api/ps reports size_vram), Node and
the browser worker, git, the audit binaries, and the knowledge base.

Exit code 0 = ready (warnings allowed), 1 = something required is missing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import httpx

from revamp.llm.registry import LOCAL_TIER
from revamp.settings import settings

OK, WARN, FAIL = "ok  ", "WARN", "FAIL"


class Report:
    def __init__(self) -> None:
        self.failed = False

    def line(self, status: str, what: str, detail: str = "") -> None:
        if status == FAIL:
            self.failed = True
        print(f"[{status}] {what}" + (f"  -  {detail}" if detail else ""))


def _ollama(path: str, payload: dict | None = None, timeout: float = 10) -> dict:
    url = settings.ollama_api_base.rstrip("/") + path
    r = httpx.post(url, json=payload, timeout=timeout) if payload is not None \
        else httpx.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def check_ollama(rep: Report, load: bool) -> None:
    try:
        ver = _ollama("/api/version")["version"]
    except Exception as e:
        rep.line(FAIL, f"Ollama at {settings.ollama_api_base}",
                 f"not reachable ({type(e).__name__}). Start Ollama, or fix OLLAMA_API_BASE")
        return
    rep.line(OK, f"Ollama {ver} at {settings.ollama_api_base}")

    # Library tags that silently resolve to THINKING variants (registry digests, 30 Sep).
    thinking_aliases = {"qwen3:4b", "qwen3-vl:4b", "qwen3:latest", "qwen3-vl:latest"}
    for tier in ("instruct", "vision"):
        tag = settings.ollama_models[tier]
        if tag in thinking_aliases or "thinking" in tag:
            rep.line(WARN, f"{tier} tier uses {tag}",
                     "that tag is a THINKING model; use the -instruct tag "
                     "(check REVAMP_OLLAMA_* / legacy REVAMP_LOCAL_MODEL in .env)")

    pulled = {m["name"] for m in _ollama("/api/tags").get("models", [])}
    needed = {tier: tag for tier, tag in settings.ollama_models.items()
              if settings.model_mode != "gemini"}
    for tier, tag in needed.items():
        agents = sorted(a for a, t in LOCAL_TIER.items()
                        if settings.local_tier_overrides.get(a, t) == tier)
        if tag in pulled:
            rep.line(OK, f"model {tag} ({tier})", f"used by {len(agents)} agents")
        else:
            rep.line(FAIL, f"model {tag} ({tier}) not pulled", f"run: ollama pull {tag}")

    if not load:
        rep.line(WARN, "GPU placement not checked", "run `revamp doctor --gpu` to load each model")
        return
    for tier, tag in needed.items():
        if tag not in pulled:
            continue
        try:
            # A 1-token generation loads the model with the same options the agents use.
            opts = {"num_ctx": settings.ollama_num_ctx[tier]}
            if settings.ollama_num_gpu >= 0:
                opts["num_gpu"] = settings.ollama_num_gpu
            _ollama("/api/generate", {"model": tag, "prompt": "ok", "stream": False,
                                      "options": {**opts, "num_predict": 1},
                                      "keep_alive": "5m", "think": False}, timeout=600)
            running = {m["name"]: m for m in _ollama("/api/ps").get("models", [])}
            m = running.get(tag)
            if not m or not m.get("size"):
                rep.line(WARN, f"GPU placement of {tag}", "model not listed by /api/ps")
                continue
            share = m.get("size_vram", 0) / m["size"]
            gb = m["size"] / 2**30
            if share >= 0.99:
                rep.line(OK, f"{tag} on GPU", f"100% of {gb:.1f} GB in VRAM")
            elif share > 0:
                rep.line(WARN, f"{tag} partly on CPU",
                         f"{share:.0%} of {gb:.1f} GB in VRAM; lower REVAMP_NUM_CTX_* "
                         "or use a smaller model")
            else:
                rep.line(FAIL, f"{tag} running on CPU",
                         "no VRAM used: check the GPU driver / CUDA, or `ollama ps`")
        except Exception as e:
            rep.line(FAIL, f"loading {tag}", f"{type(e).__name__}: {str(e)[:160]}")


def check_tools(rep: Report) -> None:
    for exe, why in (("node", "Lighthouse and the browser worker"), ("git", "code audit clones")):
        path = shutil.which(exe)
        rep.line(OK if path else FAIL, exe, path or f"missing; needed for {why}")
    worker = settings.root / "browser_worker" / "node_modules" / "playwright"
    rep.line(OK if worker.is_dir() else WARN, "browser worker (Playwright + axe)",
             "installed" if worker.is_dir() else "run scripts/setup (npm install in browser_worker)")
    for name in ("osv-scanner", "scc"):
        found = any((settings.tools_bin / n).is_file() for n in (name, f"{name}.exe")) \
            or shutil.which(name)
        rep.line(OK if found else WARN, name, "found" if found else "run scripts/setup")
    try:
        import lizard  # noqa: F401
        rep.line(OK, "lizard")
    except ImportError:
        rep.line(WARN, "lizard", "pip install -r requirements.txt")


def check_env(rep: Report) -> None:
    rep.line(OK if sys.version_info[:2] == (3, 11) else WARN,
             f"Python {sys.version.split()[0]}", "project is pinned to 3.11")
    rep.line(OK if (settings.root / ".env").is_file() else WARN, ".env",
             "found" if (settings.root / ".env").is_file() else "copy .env.example to .env")
    rep.line(OK, f"model mode: {settings.model_mode}",
             ", ".join(f"{k}={v}" for k, v in settings.ollama_models.items())
             if settings.model_mode != "gemini" else settings.gemini_model)
    import os
    if settings.model_mode in {"hybrid", "gemini"} and not os.getenv("GOOGLE_API_KEY"):
        rep.line(FAIL, "GOOGLE_API_KEY", f"required for mode {settings.model_mode}")
    rep.line(OK if settings.github_token else WARN, "GITHUB_TOKEN",
             "set" if settings.github_token else "unauthenticated GitHub search: 10 req/min")
    rep.line(OK if settings.psi_api_key else WARN, "PSI_API_KEY",
             "set" if settings.psi_api_key else "performance falls back to local Lighthouse")


def check_kb(rep: Report) -> None:
    from revamp.kb import KnowledgeBase
    from revamp.products import list_products
    kb = KnowledgeBase(settings.kb_path, "evaluator")
    for p in list_products():
        n = len(kb.findings(p))
        cons = len(kb.constraints(p))
        status = OK if n else WARN
        rep.line(status, f"product {p}", f"{n} findings, {cons} private constraints"
                 + ("" if n else f"  (run: python -m revamp audit {p})"))


def gpu_hardware(rep: Report) -> None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        rep.line(WARN, "nvidia-smi", "not found (fine on AMD/Apple; Ollama reports placement)")
        return
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total,memory.used",
                              "--format=csv,noheader"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
        rep.line(OK, "GPU", out or "nvidia-smi returned nothing")
    except Exception as e:
        rep.line(WARN, "nvidia-smi", str(e)[:120])


def run(load_models: bool = False) -> int:
    rep = Report()
    print("== environment"); check_env(rep)
    print("== GPU"); gpu_hardware(rep)
    if settings.model_mode != "gemini":
        print("== Ollama"); check_ollama(rep, load_models)
    print("== audit tooling"); check_tools(rep)
    print("== knowledge base"); check_kb(rep)
    print("\nREADY" if not rep.failed else "\nNOT READY: fix the FAIL lines above")
    return 1 if rep.failed else 0
