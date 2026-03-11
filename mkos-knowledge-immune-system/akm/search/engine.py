"""Hybrid search engine: FTS5 (BM25) + sqlite-vec (dense) with RRF fusion."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


@dataclass
class SearchResult:
    chunk_id: int
    heading: str
    content: str
    score: float
    file_path: str
    document_title: str
    project_slug: str
    project_name: str

    def snippet(self, max_chars: int = 300) -> str:
        """Return a truncated content snippet without the contextual prefix."""
        text = self.content
        # Strip contextual prefix [Project: ... | File: ...]
        if text.startswith("[Project:"):
            nl = text.find("\n")
            if nl > 0:
                text = text[nl + 1:]
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text


def sanitize_fts_query(text: str) -> str:
    """Sanitize arbitrary text for use in FTS5 MATCH queries.

    Splits into words, removes non-alphanumeric characters,
    quotes each term, and joins with OR for relevance matching.
    """
    terms = re.sub(r'[^\w\s]', ' ', text).split()
    if not terms:
        return '""'
    # Quote each term and OR them for broad relevance matching
    return " OR ".join(f'"{t}"' for t in terms[:30] if t)


def reciprocal_rank_fusion(
    *rankings: list[int],
    k: int = 60,
) -> list[tuple[int, float]]:
    """Combine multiple rankings via Reciprocal Rank Fusion.

    Each ranking is a list of chunk_ids in rank order.
    Returns (chunk_id, rrf_score) sorted by score descending.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _has_vec_table(conn: sqlite3.Connection) -> bool:
    """Check if chunks_vec table exists."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_vec'"
    ).fetchone()
    return row is not None


class SearchEngine:
    """Hybrid search: FTS5 (sparse) + sqlite-vec (dense) with RRF fusion."""

    # FTS5 special characters that need escaping
    _SPECIAL = re.compile(r'[*(){}[\]^~\\]')

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._vec_available = _has_vec_table(conn)

    def search(self, query: str, limit: int = 10,
               project: str | None = None) -> list[SearchResult]:
        """Search indexed knowledge. Uses hybrid BM25+vector if available."""
        if self._vec_available:
            return self._hybrid_search(query, limit, project)
        return self._fts_search(query, limit, project)

    def search_related(self, content: str, exclude_id: int,
                       limit: int = 5,
                       prefer_fts: bool = False) -> list[tuple[int, str, str]]:
        """Find chunks related to given content. Returns (id, heading, content).

        Uses vector search if available, falls back to FTS.
        If prefer_fts=True, tries FTS first (better for unknown/proprietary entities).
        """
        if prefer_fts:
            fts_results = self._fts_related(content, exclude_id, limit)
            if fts_results:
                return fts_results
            # Fall through to vector if FTS finds nothing

        if self._vec_available:
            try:
                from akm.search.embeddings import embed_single, serialize_f32
                query_emb = embed_single(content[:1000])
                rows = self.conn.execute(
                    "SELECT v.chunk_id, v.distance FROM chunks_vec v "
                    "WHERE v.embedding MATCH ? AND v.chunk_id != ? "
                    "ORDER BY v.distance LIMIT ?",
                    (serialize_f32(query_emb), exclude_id, limit),
                ).fetchall()
                result = []
                for r in rows:
                    chunk = self.conn.execute(
                        "SELECT id, heading, content FROM chunks WHERE id = ?",
                        (r[0],),
                    ).fetchone()
                    if chunk:
                        result.append((chunk["id"], chunk["heading"], chunk["content"]))
                return result
            except Exception:
                pass

        # Fallback to FTS
        return self._fts_related(content, exclude_id, limit)

    def _fts_related(self, content: str, exclude_id: int,
                     limit: int = 5) -> list[tuple[int, str, str]]:
        """FTS-based related chunk search (lexical/keyword matching)."""
        query_text = sanitize_fts_query(content[:200])
        try:
            rows = self.conn.execute(
                "SELECT c.id, c.heading, c.content FROM chunks c "
                "JOIN chunks_fts ON chunks_fts.rowid = c.id "
                "WHERE chunks_fts MATCH ? AND c.id != ? "
                "ORDER BY rank LIMIT ?",
                (query_text, exclude_id, limit),
            ).fetchall()
            return [(r["id"], r["heading"], r["content"]) for r in rows]
        except sqlite3.OperationalError:
            return []

    def _hybrid_search(self, query: str, limit: int,
                       project: str | None) -> list[SearchResult]:
        """RRF fusion of FTS5 + vector search."""
        # Sparse: FTS5
        fts_ids = self._fts_chunk_ids(query, limit=limit * 2, project=project)

        # Dense: vector search
        vec_ids = []
        try:
            from akm.search.embeddings import embed_single, serialize_f32
            query_emb = embed_single(query)
            rows = self.conn.execute(
                "SELECT chunk_id FROM chunks_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (serialize_f32(query_emb), limit * 2),
            ).fetchall()
            vec_ids = [r[0] for r in rows]
        except Exception:
            pass

        if not vec_ids:
            return self._fts_search(query, limit, project)

        # RRF fusion
        fused = reciprocal_rank_fusion(fts_ids, vec_ids)

        # Fetch chunk data for top results
        results = []
        for chunk_id, rrf_score in fused[:limit]:
            row = self.conn.execute(
                "SELECT c.id as chunk_id, c.heading, c.content, "
                "d.file_path, d.title as doc_title, "
                "p.slug as project_slug, p.name as project_name "
                "FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "JOIN projects p ON p.id = d.project_id "
                "WHERE c.id = ?",
                (chunk_id,),
            ).fetchone()
            if row:
                results.append(SearchResult(
                    chunk_id=row["chunk_id"],
                    heading=row["heading"],
                    content=row["content"],
                    score=rrf_score,
                    file_path=row["file_path"],
                    document_title=row["doc_title"],
                    project_slug=row["project_slug"],
                    project_name=row["project_name"],
                ))
        return results

    def _fts_search(self, query: str, limit: int,
                    project: str | None) -> list[SearchResult]:
        """Pure FTS5 search (fallback)."""
        fts_query = self._prepare_query(query)
        if not fts_query:
            return []

        params: list = [fts_query]
        project_filter = ""
        if project:
            project_filter = "AND p.slug = ?"
            params.append(project)
        params.append(limit)

        sql = f"""
            SELECT c.id as chunk_id, c.heading, c.content, c.token_count,
                   d.file_path, d.title as doc_title,
                   p.slug as project_slug, p.name as project_name,
                   rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            JOIN projects p ON p.id = d.project_id
            WHERE chunks_fts MATCH ?
            {project_filter}
            ORDER BY rank
            LIMIT ?
        """

        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

        return [
            SearchResult(
                chunk_id=r["chunk_id"],
                heading=r["heading"],
                content=r["content"],
                score=r["rank"],
                file_path=r["file_path"],
                document_title=r["doc_title"],
                project_slug=r["project_slug"],
                project_name=r["project_name"],
            )
            for r in rows
        ]

    def _fts_chunk_ids(self, query: str, limit: int,
                       project: str | None = None) -> list[int]:
        """Get ranked chunk IDs from FTS5."""
        fts_query = self._prepare_query(query)
        if not fts_query:
            return []

        params: list = [fts_query]
        project_filter = ""
        if project:
            project_filter = "AND p.slug = ?"
            params.append(project)
        params.append(limit)

        sql = f"""
            SELECT c.id
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            JOIN projects p ON p.id = d.project_id
            WHERE chunks_fts MATCH ?
            {project_filter}
            ORDER BY rank
            LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, params).fetchall()
            return [r[0] for r in rows]
        except sqlite3.OperationalError:
            return []

    def stats(self) -> dict:
        """Return index statistics."""
        projects = self.conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
        documents = self.conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
        chunks = self.conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
        tokens = self.conn.execute(
            "SELECT COALESCE(SUM(token_count), 0) as c FROM chunks"
        ).fetchone()["c"]

        vec_count = 0
        if self._vec_available:
            try:
                vec_count = self.conn.execute(
                    "SELECT COUNT(*) FROM chunks_vec"
                ).fetchone()[0]
            except Exception:
                pass

        return {
            "projects": projects,
            "documents": documents,
            "chunks": chunks,
            "total_tokens": tokens,
            "vector_embeddings": vec_count,
            "hybrid_search": self._vec_available,
        }

    def _prepare_query(self, query: str) -> str:
        """Prepare query for FTS5 MATCH."""
        query = query.strip()
        if not query:
            return ""
        # If user used quotes, pass through
        if '"' in query:
            return query
        # Escape special chars and join terms with implicit AND
        terms = query.split()
        safe = [self._SPECIAL.sub("", t) for t in terms if t]
        return " ".join(f'"{t}"' for t in safe if t)
