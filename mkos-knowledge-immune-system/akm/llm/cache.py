"""LLM response cache for reproducible and affordable benchmark runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from akm.llm.client import ClaudeClient, LLMResponse


class CachedClaudeClient(ClaudeClient):
    """Wraps ClaudeClient with a SQLite-backed response cache.

    Cached at the analyze() level. extract_json() benefits automatically
    since it calls analyze() internally.
    """

    def __init__(
        self,
        delegate: ClaudeClient,
        cache_path: str = ".mkos_llm_cache.db",
    ) -> None:
        # Don't call super().__init__() -- we delegate everything
        self._delegate = delegate
        self._original_analyze = delegate.analyze  # Save unbound reference for cache misses
        self._cache_conn = sqlite3.connect(cache_path)
        self._cache_conn.row_factory = sqlite3.Row
        self._init_schema()
        self.cache_hits = 0
        self.cache_misses = 0

    def _init_schema(self) -> None:
        self._cache_conn.execute(
            "CREATE TABLE IF NOT EXISTS llm_cache ("
            "  cache_key TEXT PRIMARY KEY,"
            "  model TEXT,"
            "  content TEXT,"
            "  input_tokens INTEGER,"
            "  output_tokens INTEGER,"
            "  created_at TEXT DEFAULT (datetime('now'))"
            ")"
        )
        self._cache_conn.commit()

    @staticmethod
    def _make_key(model: str, system_prompt: str, user_content: str,
                  temperature: float, max_tokens: int | None) -> str:
        raw = f"{model}|{system_prompt}|{user_content}|{temperature}|{max_tokens}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def analyze(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        key = self._make_key(
            self._delegate.model, system_prompt, user_content, temperature, max_tokens
        )

        # Check cache
        row = self._cache_conn.execute(
            "SELECT content, input_tokens, output_tokens FROM llm_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()

        if row:
            self.cache_hits += 1
            # Still track tokens for stats consistency
            self._delegate._total_input_tokens += row["input_tokens"]
            self._delegate._total_output_tokens += row["output_tokens"]
            self._delegate._call_count += 1
            return LLMResponse(
                content=row["content"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                model=self._delegate.model,
                duration_seconds=0.0,
            )

        # Cache miss -- call real API (use saved reference to avoid recursion)
        self.cache_misses += 1
        result = self._original_analyze(
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Store in cache
        self._cache_conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, model, content, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, self._delegate.model, result.content, result.input_tokens, result.output_tokens),
        )
        self._cache_conn.commit()

        return result

    def extract_json(self, system_prompt: str, user_content: str,
                     temperature: float = 0.0, max_tokens: int | None = None,
                     retries: int = 2) -> dict | list:
        # Delegate to the real extract_json but with our cached analyze()
        # We temporarily swap the delegate's analyze to use ours
        original_analyze = self._delegate.analyze
        self._delegate.analyze = self.analyze
        try:
            return self._delegate.extract_json(
                system_prompt=system_prompt,
                user_content=user_content,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
            )
        finally:
            self._delegate.analyze = original_analyze

    @property
    def model(self) -> str:
        return self._delegate.model

    @property
    def total_cost_usd(self) -> float:
        return self._delegate.total_cost_usd

    @property
    def call_count(self) -> int:
        return self._delegate.call_count

    def stats(self) -> dict:
        base = self._delegate.stats()
        base["cache_hits"] = self.cache_hits
        base["cache_misses"] = self.cache_misses
        return base

    def clear_cache(self) -> int:
        """Clear all cached responses. Returns count of deleted entries."""
        count = self._cache_conn.execute("SELECT COUNT(*) as c FROM llm_cache").fetchone()["c"]
        self._cache_conn.execute("DELETE FROM llm_cache")
        self._cache_conn.commit()
        return count

    def cache_size(self) -> int:
        return self._cache_conn.execute("SELECT COUNT(*) as c FROM llm_cache").fetchone()["c"]
