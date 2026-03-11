"""Embedding generation and vector search via fastembed + sqlite-vec."""

from __future__ import annotations

import sqlite3
import struct
from typing import TYPE_CHECKING

import numpy as np
import sqlite_vec

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Lazy-loaded singleton to avoid loading model on import
_model = None
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[NDArray[np.float32]]:
    """Generate embeddings for a list of texts."""
    model = _get_model()
    return list(model.embed(texts))


def embed_single(text: str) -> NDArray[np.float32]:
    """Generate embedding for a single text."""
    return embed_texts([text])[0]


def serialize_f32(vector: NDArray[np.float32]) -> bytes:
    """Serialize numpy float32 array to bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector.astype(np.float32))


def enable_vec(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension into a connection."""
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def create_vec_table(conn: sqlite3.Connection) -> None:
    """Create the virtual vector table for chunk embeddings."""
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
        f"  chunk_id INTEGER PRIMARY KEY,"
        f"  embedding float[{EMBEDDING_DIM}]"
        f")"
    )
    conn.commit()


def upsert_embedding(conn: sqlite3.Connection, chunk_id: int,
                     embedding: NDArray[np.float32]) -> None:
    """Insert or replace a chunk embedding."""
    conn.execute(
        "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, serialize_f32(embedding)),
    )


def embed_all_chunks(conn: sqlite3.Connection, batch_size: int = 64) -> int:
    """Embed all chunks that don't have embeddings yet."""
    # Get chunks without embeddings
    existing = set()
    try:
        rows = conn.execute("SELECT chunk_id FROM chunks_vec").fetchall()
        existing = {r[0] for r in rows}
    except sqlite3.OperationalError:
        pass

    chunks = conn.execute("SELECT id, content FROM chunks").fetchall()
    to_embed = [(r["id"], r["content"]) for r in chunks if r["id"] not in existing]

    if not to_embed:
        return 0

    count = 0
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i:i + batch_size]
        texts = [content[:1000] for _, content in batch]  # Truncate for embedding
        embeddings = embed_texts(texts)
        for (chunk_id, _), emb in zip(batch, embeddings):
            upsert_embedding(conn, chunk_id, emb)
        count += len(batch)

    conn.commit()
    return count


def vector_search(conn: sqlite3.Connection, query: str,
                  limit: int = 10) -> list[tuple[int, float]]:
    """Search chunks by vector similarity. Returns (chunk_id, distance) pairs."""
    query_emb = embed_single(query)
    rows = conn.execute(
        "SELECT chunk_id, distance FROM chunks_vec "
        "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (serialize_f32(query_emb), limit),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]
