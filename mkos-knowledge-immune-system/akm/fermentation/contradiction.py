"""Contradiction detection between fermenting content and existing knowledge."""

from __future__ import annotations

from dataclasses import dataclass

from akm.llm.client import ClaudeClient

CONTRADICTION_SYSTEM_PROMPT = """\
You are a contradiction detection specialist. Given NEW content and a set of \
EXISTING knowledge chunks, identify specific contradictions.

For each contradiction found, provide:
- Which specific claim in the new content conflicts
- Which specific claim in the existing content it conflicts with
- Severity: "minor" (nuance difference), "major" (factual conflict), "critical" (fundamental incompatibility)
- A suggested resolution

If there are no contradictions, return an empty array.

Respond with JSON:
[
  {
    "new_excerpt": "the specific claim from new content",
    "existing_chunk_id": 123,
    "existing_excerpt": "the conflicting claim from existing content",
    "severity": "minor|major|critical",
    "explanation": "why these conflict",
    "suggested_resolution": "how to resolve"
  }
]"""


@dataclass
class Contradiction:
    fermenting_content_excerpt: str
    existing_chunk_id: int
    existing_content_excerpt: str
    severity: str
    explanation: str
    suggested_resolution: str


class ContradictionDetector:
    """Detect contradictions between fermenting content and existing knowledge."""

    def __init__(self, llm: ClaudeClient) -> None:
        self.llm = llm

    def detect(
        self, fermenting_content: str, related_chunks: list[dict]
    ) -> list[Contradiction]:
        """Identify contradictions between new and existing knowledge."""
        if not related_chunks:
            return []

        # Build existing knowledge context
        existing_ctx = ""
        for chunk in related_chunks[:5]:
            existing_ctx += (
                f"\n[Chunk ID: {chunk.get('id', chunk.get('chunk_id', 0))}] "
                f"(Heading: {chunk.get('heading', 'N/A')})\n"
                f"{chunk.get('content', '')[:800]}\n"
            )

        raw = self.llm.extract_json(
            system_prompt=CONTRADICTION_SYSTEM_PROMPT,
            user_content=(
                f"NEW CONTENT:\n{fermenting_content[:2000]}\n\n"
                f"EXISTING KNOWLEDGE:{existing_ctx}"
            ),
        )

        contradictions = []
        items = raw if isinstance(raw, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            severity = item.get("severity", "minor")
            if severity not in ("minor", "major", "critical"):
                severity = "minor"
            contradictions.append(
                Contradiction(
                    fermenting_content_excerpt=item.get("new_excerpt", ""),
                    existing_chunk_id=int(item.get("existing_chunk_id", 0)),
                    existing_content_excerpt=item.get("existing_excerpt", ""),
                    severity=severity,
                    explanation=item.get("explanation", ""),
                    suggested_resolution=item.get("suggested_resolution", ""),
                )
            )
        return contradictions
