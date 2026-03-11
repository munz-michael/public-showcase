"""RAG pipeline for knowledge-base-grounded question answering.

Uses SearchEngine to retrieve relevant chunks, then LLM to generate
answers grounded in the retrieved context.
"""

from __future__ import annotations

import sqlite3

from akm.llm.client import ClaudeClient
from akm.search.engine import SearchEngine


class RAGPipeline:
    """Retrieve-then-generate QA pipeline over the knowledge base."""

    SYSTEM_PROMPT = (
        "You are a knowledge base assistant. Answer the question using ONLY "
        "the provided context chunks. If the context doesn't contain enough "
        "information, say so explicitly.\n\n"
        "Rules:\n"
        "- Cite chunk numbers [1], [2] etc. when using information\n"
        "- Do not add information beyond what's in the context\n"
        "- If chunks contradict each other, note the contradiction\n"
        "- Be concise and factual\n"
    )

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        top_k: int = 5,
    ) -> None:
        self.conn = conn
        self.llm = llm
        self.engine = SearchEngine(conn)
        self.top_k = top_k

    def answer(self, question: str) -> dict:
        """Answer a question using RAG.

        Returns dict with: answer, chunks_used, chunk_ids
        Uses OR-based FTS for natural language questions (more recall).
        """
        from akm.search.engine import sanitize_fts_query

        # Use OR-based search for better recall on natural language questions
        fts_query = sanitize_fts_query(question)
        results = []
        try:
            rows = self.conn.execute(
                "SELECT c.id as chunk_id, c.heading, c.content, rank as score "
                "FROM chunks_fts "
                "JOIN chunks c ON c.id = chunks_fts.rowid "
                "WHERE chunks_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, self.top_k),
            ).fetchall()
            results = [type('Result', (), dict(r))() for r in rows]
        except Exception:
            pass

        # Fallback to standard search
        if not results:
            results = self.engine.search(question, limit=self.top_k)

        if not results:
            return {
                "answer": "No relevant information found in the knowledge base.",
                "chunks_used": [],
                "chunk_ids": [],
            }

        context = ""
        for i, r in enumerate(results, 1):
            context += f"\n[{i}] {r.heading}:\n{r.content[:500]}\n"

        user_content = f"CONTEXT:{context}\n\nQUESTION: {question}"

        response = self.llm.analyze(
            system_prompt=self.SYSTEM_PROMPT,
            user_content=user_content,
            temperature=0.1,
        )

        return {
            "answer": response.content,
            "chunks_used": [
                {"id": r.chunk_id, "heading": r.heading, "score": r.score}
                for r in results
            ],
            "chunk_ids": [r.chunk_id for r in results],
        }
