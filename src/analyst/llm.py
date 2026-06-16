"""Anthropic client wrapper: forced tool-use + plain text, with token capture.

Every call returns its token usage so the graph can instrument cost per stage.
Forced tool-use (tool_choice = {"type": "tool", "name": ...}) is how we get a
valid enum/SQL string back instead of parsing free text.
"""

from __future__ import annotations

from typing import Any

import anthropic

from .config import Config


def _usage(resp: anthropic.types.Message) -> dict[str, int]:
    """Pull real token counts off the response (never estimated)."""
    u = resp.usage
    return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}


class LLM:
    """Thin Haiku client. One instance per run, reused across nodes."""

    def __init__(self, cfg: Config) -> None:
        self._client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self._model = cfg.model
        self._max_tokens = cfg.max_tokens

    def tool_call(
        self, *, system: str, user: str, tool: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Force `tool`; return (parsed tool input, token usage)."""
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user}],
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        return dict(block.input), _usage(resp)

    def text(self, *, system: str, user: str) -> tuple[str, dict[str, int]]:
        """Plain completion; return (text, token usage)."""
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return text, _usage(resp)
