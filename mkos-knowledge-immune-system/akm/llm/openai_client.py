"""OpenAI API wrapper matching ClaudeClient interface for multi-model benchmarks."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from akm.llm.client import LLMResponse

logger = logging.getLogger(__name__)

# Pricing per million tokens
_OPENAI_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
}


class OpenAIClient:
    """OpenAI API client matching ClaudeClient interface.

    Provides analyze() and extract_json() with the same signatures,
    allowing drop-in replacement for multi-model benchmarks.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 1024,
        api_key: str | None = None,
    ) -> None:
        try:
            import openai
        except ImportError:
            raise ImportError("pip install openai  -- required for OpenAI multi-model benchmarks")

        self.model = model
        self.max_tokens = max_tokens
        self._client = openai.OpenAI(api_key=api_key)
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
        """Single-turn analysis call matching ClaudeClient.analyze()."""
        t0 = time.time()
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        duration = time.time() - t0

        content = response.choices[0].message.content if response.choices else ""
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        result = LLMResponse(
            content=content or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            duration_seconds=duration,
        )

        self._total_input_tokens += result.input_tokens
        self._total_output_tokens += result.output_tokens
        self._call_count += 1

        logger.debug(
            "OpenAI call #%d: %d in / %d out tokens, %.1fs",
            self._call_count, result.input_tokens, result.output_tokens, duration,
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
        """Call OpenAI and parse response as JSON. Same interface as ClaudeClient."""
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
        prices = _OPENAI_PRICING.get(self.model, {"input": 2.50, "output": 10.00})
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
