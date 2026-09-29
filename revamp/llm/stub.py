"""ScriptedLlm: a deterministic fake model for tests and offline demos.

It answers from a function of the request, so the whole workflow can run end to end
with no Ollama, no Gemini key and no network. Tests use it to check orchestration
logic (loops, caps, routing) independently of model quality.
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator, Callable

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models._capabilities import LlmCapabilities
from google.genai import types
from pydantic import ConfigDict, Field

Responder = Callable[[LlmRequest], "str | types.Part | list[types.Part]"]


def last_user_text(req: LlmRequest) -> str:
    for c in reversed(req.contents):
        for p in c.parts or []:
            if p.text:
                return p.text
    return ""


class ScriptedLlm(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Unique per instance, so two stubs with different scripts never share cache keys.
    model: str = Field(default_factory=lambda: f"scripted-{uuid.uuid4().hex[:8]}")
    responder: Responder
    calls: int = 0

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        out = self.responder(llm_request)
        if isinstance(out, str):
            parts = [types.Part(text=out)]
        elif isinstance(out, types.Part):
            parts = [out]
        else:
            parts = list(out)
        yield LlmResponse(
            content=types.Content(role="model", parts=parts),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10, candidates_token_count=5),
        )
