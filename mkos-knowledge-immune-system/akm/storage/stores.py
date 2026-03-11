"""Data stores for projects, documents, and chunks."""

from __future__ import annotations

import json
import sqlite3

from akm.ingestion.chunker import Chunk


class ProjectStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, slug: str, name: str, path: str,
               project_type: str = "", description: str = "",
               tags: list[str] | None = None) -> int:
        self.conn.execute(
            "INSERT INTO projects (slug, name, path, project_type, description, tags) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET "
            "name=excluded.name, path=excluded.path, "
            "project_type=excluded.project_type, description=excluded.description, "
            "tags=excluded.tags, last_scanned_at=datetime('now')",
            (slug, name, path, project_type, description, json.dumps(tags or [])),
        )
        row = self.conn.execute("SELECT id FROM projects WHERE slug = ?", (slug,)).fetchone()
        return row["id"]

    def get_all(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.*, "
            "(SELECT COUNT(*) FROM documents d WHERE d.project_id = p.id) as doc_count, "
            "(SELECT COALESCE(SUM(c.token_count), 0) FROM chunks c "
            " JOIN documents d ON d.id = c.document_id WHERE d.project_id = p.id) as token_count "
            "FROM projects p ORDER BY p.name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_slug(self, slug: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None


class DocumentStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, project_id: int, file_path: str, file_type: str,
               title: str, file_size: int, line_count: int,
               content_hash: str, modified_at: str) -> int:
        # Check if exists and hash changed
        existing = self.conn.execute(
            "SELECT id, content_hash FROM documents WHERE file_path = ?",
            (file_path,),
        ).fetchone()

        if existing and existing["content_hash"] == content_hash:
            return existing["id"]  # unchanged

        if existing:
            # Delete old chunks (triggers will clean FTS)
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (existing["id"],))
            self.conn.execute(
                "UPDATE documents SET title=?, file_size=?, line_count=?, "
                "content_hash=?, indexed_at=datetime('now'), modified_at=? "
                "WHERE id=?",
                (title, file_size, line_count, content_hash, modified_at, existing["id"]),
            )
            return existing["id"]

        cursor = self.conn.execute(
            "INSERT INTO documents (project_id, file_path, file_type, title, "
            "file_size, line_count, content_hash, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, file_path, file_type, title, file_size, line_count,
             content_hash, modified_at),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def get_by_path(self, file_path: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM documents WHERE file_path = ?", (file_path,)
        ).fetchone()
        return dict(row) if row else None

    def delete_missing(self, project_id: int, existing_paths: set[str]) -> int:
        """Delete documents whose files no longer exist."""
        rows = self.conn.execute(
            "SELECT id, file_path FROM documents WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        deleted = 0
        for row in rows:
            if row["file_path"] not in existing_paths:
                self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (row["id"],))
                self.conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
                deleted += 1
        return deleted


class ChunkStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert_batch(self, document_id: int, chunks: list[Chunk]) -> int:
        for chunk in chunks:
            self.conn.execute(
                "INSERT INTO chunks (document_id, chunk_index, heading, content, token_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (document_id, chunk.chunk_index, chunk.heading, chunk.content, chunk.token_count),
            )
        return len(chunks)
