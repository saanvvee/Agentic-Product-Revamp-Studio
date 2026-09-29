"""Run one agent on one prompt and get validated structured output back.

Every agent call in the system goes through `ask()`. It runs the agent in its own
short-lived ADK session, so an agent sees only what the calling workflow node chose
to show it: no shared conversation history, and nothing from session state it was
not given. That is how context stays small (qwen3:4b) and how the Client's private
constraints stay out of every team agent's view.

Output validation is in code: if the model returns JSON that does not fit the
schema, we retry once with the validation error appended, then give up loudly.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import TypeVar

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from revamp import observe

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AgentOutputError(RuntimeError):
    pass


def _extract_json(text: str) -> str:
    """Models sometimes wrap JSON in ```json fences or <think> blocks; strip both."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=0)
    return text[start:]


async def _run_once(agent: LlmAgent, parts: list[types.Part]) -> tuple[object, str]:
    app = f"ask_{agent.name}"
    runner = InMemoryRunner(agent=agent, app_name=app)
    uid = "revamp"
    session = await runner.session_service.create_session(app_name=app, user_id=uid,
                                                          session_id=uuid.uuid4().hex)
    text_chunks: list[str] = []
    async for ev in runner.run_async(user_id=uid, session_id=session.id,
                                     new_message=types.Content(role="user", parts=parts)):
        if ev.content and ev.content.parts and ev.author == agent.name:
            text_chunks += [p.text for p in ev.content.parts if p.text and not p.thought]
    session = await runner.session_service.get_session(app_name=app, user_id=uid,
                                                       session_id=session.id)
    structured = session.state.get(agent.output_key) if agent.output_key else None
    return structured, "".join(text_chunks)


async def ask(agent: LlmAgent, prompt: str, schema: type[T],
              images: list[tuple[bytes, str]] = ()) -> T:
    """`images`: (bytes, mime type) pairs, sent as inline parts (Journey Auditor)."""
    parts = [types.Part(text=prompt)] + [
        types.Part(inline_data=types.Blob(data=b, mime_type=m)) for b, m in images]
    model = getattr(agent.model, "model", str(agent.model))
    observe.emit("agent_started", agent=agent.name, model=model, prompt=prompt[:6000],
                 images=len(images), schema=schema.__name__)
    t0 = time.perf_counter()
    last_err = ""
    for attempt in range(2):
        if attempt:
            parts = parts + [types.Part(text=(
                "Your previous answer did not match the required JSON schema: "
                f"{last_err[:600]}\nAnswer again with valid JSON only."))]
        structured, text = await _run_once(agent, parts)
        candidate = structured if structured is not None else _extract_json(text)
        try:
            if isinstance(candidate, str):
                out = schema.model_validate_json(candidate)
            else:
                out = schema.model_validate(candidate)
            observe.emit("agent_finished", agent=agent.name, model=model,
                         output=out.model_dump(mode="json"), attempts=attempt + 1,
                         ms=round((time.perf_counter() - t0) * 1000))
            return out
        except (ValidationError, ValueError) as e:
            last_err = str(e)
            log.warning("%s output invalid (attempt %d): %s", agent.name, attempt + 1,
                        last_err[:200])
    observe.emit("agent_error", agent=agent.name, error=last_err[:500])
    raise AgentOutputError(f"{agent.name} failed schema {schema.__name__}: {last_err[:400]}")


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, default=str)
