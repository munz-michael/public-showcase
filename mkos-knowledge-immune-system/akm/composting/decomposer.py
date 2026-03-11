"""LLM-based decomposition of outdated knowledge into reusable nutrients."""

from __future__ import annotations

from dataclasses import dataclass

from akm.llm.client import ClaudeClient

DECOMPOSE_SYSTEM_PROMPT = """\
You are a knowledge decomposition specialist. You receive a piece of knowledge \
that has been flagged as potentially outdated (high entropy score).

Your task is to extract REUSABLE nutrients -- principles, patterns, and insights \
that survive even when specific facts become stale.

For the following knowledge chunk, extract nutrients in these categories:

1. PRINCIPLE: Core truths that remain valid regardless of specific details changing
2. PATTERN: Recurring structures or approaches that transfer to new contexts
3. ERROR_PATTERN: What went wrong and why -- mistakes that could be repeated
4. META_INSIGHT: What the obsolescence itself teaches about this domain

Rules:
- Extract 1-4 nutrients total (quality over quantity)
- Each nutrient must be REUSABLE -- it should enrich future knowledge
- Confidence: 0.0-1.0, how confident you are this nutrient is genuinely useful
- If the content has nothing worth extracting, return an empty array

Respond with a JSON array:
[
  {"type": "principle", "title": "...", "content": "...", "confidence": 0.8},
  {"type": "pattern", "title": "...", "content": "...", "confidence": 0.7}
]"""


@dataclass
class Nutrient:
    nutrient_type: str  # 'principle', 'pattern', 'error_pattern', 'meta_insight'
    title: str
    content: str
    confidence: float


class KnowledgeDecomposer:
    """Extract reusable 'nutrients' from high-entropy knowledge using Claude."""

    def __init__(self, llm: ClaudeClient) -> None:
        self.llm = llm

    def decompose(
        self,
        chunk_content: str,
        chunk_heading: str = "",
        project_context: str = "",
    ) -> list[Nutrient]:
        """Decompose a knowledge chunk into reusable nutrients."""
        user_content = ""
        if project_context:
            user_content += f"Project context: {project_context}\n\n"
        if chunk_heading:
            user_content += f"Heading: {chunk_heading}\n\n"
        user_content += f"Content:\n{chunk_content[:3000]}"

        raw = self.llm.extract_json(
            system_prompt=DECOMPOSE_SYSTEM_PROMPT,
            user_content=user_content,
        )

        nutrients = []
        items = raw if isinstance(raw, list) else raw.get("nutrients", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            nutrient_type = item.get("type", "principle")
            if nutrient_type not in ("principle", "pattern", "error_pattern", "meta_insight"):
                nutrient_type = "principle"
            nutrients.append(
                Nutrient(
                    nutrient_type=nutrient_type,
                    title=item.get("title", "Untitled"),
                    content=item.get("content", ""),
                    confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                )
            )
        return nutrients
