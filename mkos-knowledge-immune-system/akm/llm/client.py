"""Claude API wrapper for MKOS components."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import anthropic

logger = logging.getLogger(__name__)

# Pricing per million tokens (Claude Sonnet 4)
_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    duration_seconds: float = 0.0

    @property
    def cost_usd(self) -> float:
        prices = _PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        return (
            self.input_tokens * prices["input"] / 1_000_000
            + self.output_tokens * prices["output"] / 1_000_000
        )


class ClaudeClient:
    """Thin wrapper around Anthropic SDK for MKOS LLM operations."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0

    def analyze(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Single-turn analysis call."""
        t0 = time.time()
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        duration = time.time() - t0

        content = response.content[0].text if response.content else ""
        result = LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            duration_seconds=duration,
        )

        self._total_input_tokens += result.input_tokens
        self._total_output_tokens += result.output_tokens
        self._call_count += 1

        logger.debug(
            "LLM call #%d: %d in / %d out tokens, %.1fs, $%.4f",
            self._call_count, result.input_tokens, result.output_tokens,
            duration, result.cost_usd,
        )
        return result

    def extract_json(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        retries: int = 2,
    ) -> dict | list:
        """Call Claude and parse response as JSON. Retries on parse failure."""
        last_error = None
        for attempt in range(retries + 1):
            resp = self.analyze(
                system_prompt=system_prompt + "\n\nRespond ONLY with valid JSON, no markdown fences.",
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = resp.content.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                # Try to extract first JSON array or object from response
                for start_char, end_char in [("[", "]"), ("{", "}")]:
                    start = text.find(start_char)
                    if start == -1:
                        continue
                    depth = 0
                    for i, ch in enumerate(text[start:], start):
                        if ch == start_char:
                            depth += 1
                        elif ch == end_char:
                            depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start:i + 1])
                            except json.JSONDecodeError:
                                break
                last_error = e
                logger.warning("JSON parse failed (attempt %d/%d): %s", attempt + 1, retries + 1, e)

        raise ValueError(f"Failed to parse JSON after {retries + 1} attempts: {last_error}")

    @property
    def total_cost_usd(self) -> float:
        prices = _PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        return (
            self._total_input_tokens * prices["input"] / 1_000_000
            + self._total_output_tokens * prices["output"] / 1_000_000
        )

    @property
    def call_count(self) -> int:
        return self._call_count

    def stats(self) -> dict:
        return {
            "calls": self._call_count,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
        }
