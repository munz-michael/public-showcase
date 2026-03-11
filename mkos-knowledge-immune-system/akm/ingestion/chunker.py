"""Section-based chunker with contextual prefixes."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from akm.ingestion.parsers import ParsedDocument, Section


@dataclass
class Chunk:
    heading: str
    content: str
    token_count: int
    chunk_index: int


class SectionChunker:
    """Split parsed documents into search-optimized chunks."""

    def __init__(self, max_tokens: int = 512) -> None:
        self._max_tokens = max_tokens
        self._enc = tiktoken.get_encoding("cl100k_base")

    def chunk(self, doc: ParsedDocument, project_slug: str, file_name: str) -> list[Chunk]:
        """Split document sections into chunks with contextual prefixes."""
        chunks: list[Chunk] = []
        idx = 0

        for section in doc.sections:
            prefix = f"[Project: {project_slug} | File: {file_name}]\n"
            content = prefix + section.content

            tokens = self._count_tokens(content)
            if tokens <= self._max_tokens:
                chunks.append(Chunk(
                    heading=section.heading,
                    content=content,
                    token_count=tokens,
                    chunk_index=idx,
                ))
                idx += 1
            else:
                # Split on paragraphs
                sub_chunks = self._split_by_paragraphs(
                    section.heading, section.content, prefix
                )
                for sc in sub_chunks:
                    sc.chunk_index = idx
                    chunks.append(sc)
                    idx += 1

        return chunks

    def _split_by_paragraphs(self, heading: str, text: str, prefix: str) -> list[Chunk]:
        """Split large section by paragraph boundaries."""
        paragraphs = text.split("\n\n")
        chunks: list[Chunk] = []
        current = prefix

        for para in paragraphs:
            candidate = current + para + "\n\n"
            if self._count_tokens(candidate) > self._max_tokens and current != prefix:
                # Flush current
                tokens = self._count_tokens(current)
                chunks.append(Chunk(heading=heading, content=current.rstrip(), token_count=tokens, chunk_index=0))
                current = prefix + para + "\n\n"
            else:
                current = candidate

        # Final chunk
        if current.strip() and current != prefix:
            tokens = self._count_tokens(current)
            chunks.append(Chunk(heading=heading, content=current.rstrip(), token_count=tokens, chunk_index=0))

        return chunks

    def _count_tokens(self, text: str) -> int:
        return len(self._enc.encode(text, disallowed_special=()))
