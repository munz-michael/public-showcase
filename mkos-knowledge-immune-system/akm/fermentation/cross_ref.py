"""Cross-referencing between fermenting content and existing knowledge."""

from __future__ import annotations

import sqlite3

from akm.llm.client import ClaudeClient
from akm.search.engine import sanitize_fts_query

CLASSIFY_SYSTEM_PROMPT = """\
You analyze the relationship between a NEW piece of knowledge and an EXISTING piece.

Classify their relationship as one of:
- "supports": New knowledge confirms or strengthens existing knowledge
- "contradicts": New knowledge conflicts with existing knowledge
- "extends": New knowledge adds new information to existing knowledge
- "supersedes": New knowledge replaces existing knowledge (newer version)
- "unrelated": No meaningful relationship

Respond with JSON:
{"relationship": "supports|contradicts|extends|supersedes|unrelated", "similarity": 0.0-1.0, "explanation": "brief reason"}"""


class CrossReferencer:
    """Find relationships between fermenting content and existing knowledge."""

    def __init__(self, conn: sqlite3.Connection, llm: ClaudeClient) -> None:
        self.conn = conn
        self.llm = llm

    def find_references(
        self, fermentation_id: int, max_refs: int = 10
    ) -> list[dict]:
        """Find and classify relationships with existing chunks."""
        # Get fermenting content
        item = self.conn.execute(
            "SELECT raw_content, title FROM fermentation_chamber WHERE id = ?",
            (fermentation_id,),
        ).fetchone()
        if not item:
            return []

        content = item["raw_content"]
        # Use first 200 chars as FTS query (sanitized for FTS5)
        query_text = sanitize_fts_query(content[:200])

        # FTS search for related chunks
        related = self.conn.execute(
            "SELECT c.id, c.heading, c.content, c.document_id "
            "FROM chunks c "
            "JOIN chunks_fts ON chunks_fts.rowid = c.id "
            "WHERE chunks_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query_text, max_refs),
        ).fetchall()

        results = []
        for chunk in related:
            # Classify relationship via LLM
            classification = self.llm.extract_json(
                system_prompt=CLASSIFY_SYSTEM_PROMPT,
                user_content=(
                    f"NEW KNOWLEDGE:\n{content[:1500]}\n\n"
                    f"EXISTING KNOWLEDGE (heading: {chunk['heading']}):\n{chunk['content'][:1500]}"
                ),
            )

            rel_type = classification.get("relationship", "unrelated")
            if rel_type == "unrelated":
                continue

            # Store cross-reference
            self.conn.execute(
                "INSERT INTO fermentation_cross_refs "
                "(fermentation_id, related_chunk_id, relationship_type, similarity_score, explanation) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    fermentation_id,
                    chunk["id"],
                    rel_type,
                    float(classification.get("similarity", 0.0)),
                    classification.get("explanation", ""),
                ),
            )

            results.append({
                "chunk_id": chunk["id"],
                "heading": chunk["heading"],
                "relationship": rel_type,
                "similarity": classification.get("similarity", 0.0),
                "explanation": classification.get("explanation", ""),
            })

        # Update counts on fermentation item
        contradictions = sum(1 for r in results if r["relationship"] == "contradicts")
        self.conn.execute(
            "UPDATE fermentation_chamber SET cross_ref_count = ?, contradiction_count = ? "
            "WHERE id = ?",
            (len(results), contradictions, fermentation_id),
        )

        return results
