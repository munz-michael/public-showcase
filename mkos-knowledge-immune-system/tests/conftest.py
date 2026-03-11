"""Shared fixtures for MKOS tests."""

from __future__ import annotations

import sqlite3

import pytest

from akm.storage.migrations import run_migrations


class MockLLMResponse:
    def __init__(self, content: str, input_tokens: int = 100, output_tokens: int = 50):
        self.content = [type("Block", (), {"text": content})()]
        self.usage = type("Usage", (), {"input_tokens": input_tokens, "output_tokens": output_tokens})()


class MockClaudeClient:
    """Mock Claude client that returns predefined responses."""

    def __init__(self, responses: list[dict | list] | None = None) -> None:
        self._responses = responses or []
        self._call_index = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0
        self.model = "mock-model"

    def analyze(self, system_prompt: str, user_content: str,
                temperature: float = 0.3, max_tokens: int | None = None):
        from akm.llm.client import LLMResponse
        self._call_count += 1
        return LLMResponse(
            content="mock response",
            input_tokens=100,
            output_tokens=50,
            model="mock-model",
        )

    def extract_json(self, system_prompt: str, user_content: str,
                     temperature: float = 0.0, max_tokens: int | None = None,
                     retries: int = 2):
        self._call_count += 1
        if self._responses and self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        # Default: return empty list
        return []

    @property
    def total_cost_usd(self) -> float:
        return 0.0

    @property
    def call_count(self) -> int:
        return self._call_count

    def stats(self) -> dict:
        return {"calls": self._call_count, "total_cost_usd": 0.0}


@pytest.fixture
def db():
    """In-memory SQLite database with all migrations applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture
def mock_llm():
    """Mock Claude client."""
    return MockClaudeClient()


@pytest.fixture
def seeded_db(db):
    """Database with some sample data."""
    # Insert a project
    db.execute(
        "INSERT INTO projects (slug, name, path) VALUES (?, ?, ?)",
        ("test-project", "Test Project", "/tmp/test"),
    )
    # Insert a document
    db.execute(
        "INSERT INTO documents (project_id, file_path, file_type, title) VALUES (?, ?, ?, ?)",
        (1, "/tmp/test/doc1.md", "markdown", "Test Document"),
    )
    # Insert chunks
    chunks = [
        (1, 0, "Introduction", "Python 3.8 was released in 2019 with new features like walrus operator.", 15),
        (1, 1, "Current State", "The latest version of React is 18.2 released in June 2022.", 14),
        (1, 2, "Best Practices", "Always use var in JavaScript for variable declarations.", 10),
        (1, 3, "Architecture", "Microservices architecture provides better scalability than monoliths.", 12),
        (1, 4, "Testing", "Unit tests should cover at least 80% of the codebase for production quality.", 15),
    ]
    for doc_id, idx, heading, content, tokens in chunks:
        db.execute(
            "INSERT INTO chunks (document_id, chunk_index, heading, content, token_count) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, idx, heading, content, tokens),
        )
    db.commit()
    return db
