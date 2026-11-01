"""LLM provider abstraction. The assistant only ever sees read-only tools; providers just run
the tool loop and report usage. Swap providers via settings.AI_PROVIDER."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]


class ProviderError(Exception):
    """Timeout, rate limit, refusal or any provider failure → caller falls back to non-AI flow."""


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class TurnResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class AIProvider(Protocol):
    name: str

    def run(
        self,
        *,
        system: str,
        history: list[dict[str, str]],
        tools: list[ToolSpec],
        execute: ToolExecutor,
    ) -> TurnResult: ...


class AnthropicProvider:
    """Claude via the official Anthropic SDK, manual tool loop with a hard round limit."""

    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        if not settings.AI_API_KEY:
            raise ProviderError("AI_API_KEY is not configured")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(
            api_key=settings.AI_API_KEY, timeout=settings.AI_TIMEOUT_SECONDS, max_retries=1
        )

    def run(
        self,
        *,
        system: str,
        history: list[dict[str, str]],
        tools: list[ToolSpec],
        execute: ToolExecutor,
    ) -> TurnResult:
        a = self._anthropic
        messages: list[dict[str, Any]] = [dict(m) for m in history]
        tool_defs = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "strict": True,
            }
            for t in tools
        ]
        result = TurnResult(text="", model=settings.AI_MODEL)
        started = time.monotonic()
        for _ in range(settings.AI_MAX_TOOL_ROUNDS + 1):
            try:
                response = self.client.beta.messages.create(
                    model=settings.AI_MODEL,
                    max_tokens=settings.AI_MAX_OUTPUT_TOKENS,
                    system=system,
                    messages=messages,
                    tools=tool_defs,
                    output_config={"effort": settings.AI_EFFORT},
                    # Server-side refusal fallback: Anthropic routes a declined request to
                    # its recommended fallback model instead of returning the refusal.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
            except a.APITimeoutError as exc:
                raise ProviderError("timeout") from exc
            except a.RateLimitError as exc:
                raise ProviderError("rate_limited") from exc
            except a.APIStatusError as exc:
                raise ProviderError(f"api_error_{exc.status_code}") from exc
            except a.APIConnectionError as exc:
                raise ProviderError("connection_error") from exc

            result.tokens_in += response.usage.input_tokens
            result.tokens_out += response.usage.output_tokens
            result.model = response.model
            if response.stop_reason == "refusal":
                raise ProviderError("refusal")
            # Append the full content (incl. thinking blocks) to keep the turn consistent.
            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                result.text = "".join(b.text for b in response.content if b.type == "text").strip()
                break
            tool_results = []
            for block in tool_uses:
                output = execute(block.name, dict(block.input))
                result.tool_calls.append({"name": block.name, "input": dict(block.input)})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, ensure_ascii=False, default=str),
                        "is_error": bool(output.get("error")),
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        else:
            raise ProviderError("too_many_tool_rounds")
        result.latency_ms = int((time.monotonic() - started) * 1000)
        if not result.text:
            raise ProviderError("empty_response")
        return result


class ScriptedProvider:
    """Deterministic provider for tests and offline development: replays a script of tool
    calls and a final reply. Configure via `ScriptedProvider.script = [...]`."""

    name = "scripted"
    script: list[dict[str, Any]] = []

    def run(
        self,
        *,
        system: str,
        history: list[dict[str, str]],
        tools: list[ToolSpec],
        execute: ToolExecutor,
    ) -> TurnResult:
        result = TurnResult(text="", model="scripted")
        for step in self.script:
            if "tool" in step:
                result.tool_calls.append({"name": step["tool"], "input": step["input"]})
                step_out = execute(step["tool"], step["input"])
                if "expect_error" in step:
                    assert bool(step_out.get("error")) == step["expect_error"], step_out
            elif "raise" in step:
                raise ProviderError(step["raise"])
            else:
                result.text = step["reply"]
        return result


def get_provider() -> AIProvider:
    match settings.AI_PROVIDER:
        case "anthropic":
            return AnthropicProvider()
        case "scripted":
            return ScriptedProvider()
        case other:
            raise ProviderError(f"unknown provider {other}")
