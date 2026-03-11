"""Orchestrates the full knowledge composting pipeline."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from akm.composting.decomposer import KnowledgeDecomposer, Nutrient
from akm.composting.entropy import EntropyScorer
from akm.composting.nutrient_store import NutrientStore
from akm.llm.client import ClaudeClient
from akm.stigmergy.signals import PheromoneSignal, SignalType, StigmergyNetwork


@dataclass
class CompostingResult:
    chunks_scored: int = 0
    chunks_composted: int = 0
    nutrients_extracted: int = 0
    nutrients: list[Nutrient] = field(default_factory=list)
    cost_usd: float = 0.0


class KnowledgeComposter:
    """Pipeline: score entropy → identify compostable → decompose → store nutrients."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        entropy_threshold: float = 0.7,
        archive_after_composting: bool = True,
    ) -> None:
        self.conn = conn
        self.llm = llm
        self.entropy_threshold = entropy_threshold
        self.archive_after_composting = archive_after_composting
        self.scorer = EntropyScorer(conn)
        self.decomposer = KnowledgeDecomposer(llm)
        self.nutrient_store = NutrientStore(conn)
        self.stigmergy = StigmergyNetwork(conn)

    def run(
        self,
        project_slug: str | None = None,
        dry_run: bool = False,
        batch_size: int = 50,
        use_llm_scoring: bool = True,
    ) -> CompostingResult:
        """Run the full composting pipeline."""
        result = CompostingResult()

        # 1. Get chunks to score
        if project_slug:
            rows = self.conn.execute(
                "SELECT c.id FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "JOIN projects p ON p.id = d.project_id "
                "WHERE p.slug = ? LIMIT ?",
                (project_slug, batch_size),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id FROM chunks LIMIT ?", (batch_size,)
            ).fetchall()

        # 2. Score entropy
        llm_for_scoring = self.llm if use_llm_scoring else None
        for row in rows:
            self.scorer.score_chunk(row["id"], llm_for_scoring)
            result.chunks_scored += 1

        # 3. Identify compostable chunks
        compostable = self.scorer.get_compostable(self.entropy_threshold)

        if dry_run:
            result.chunks_composted = len(compostable)
            return result

        # 4. Decompose each and extract nutrients
        for chunk_data in compostable:
            chunk_id = chunk_data["chunk_id"]
            nutrients = self.decomposer.decompose(
                chunk_content=chunk_data["content"],
                chunk_heading=chunk_data.get("heading", ""),
            )

            # Store nutrients
            for nutrient in nutrients:
                self.nutrient_store.insert(
                    nutrient,
                    source_chunk_id=chunk_id,
                    source_document_id=chunk_data.get("document_id"),
                )

            # Log composting event
            self.conn.execute(
                "INSERT INTO compost_log "
                "(chunk_id, document_id, entropy_score_at_composting, nutrients_extracted) "
                "VALUES (?, ?, ?, ?)",
                (chunk_id, chunk_data.get("document_id", 0),
                 chunk_data["entropy_score"], len(nutrients)),
            )

            result.chunks_composted += 1
            result.nutrients_extracted += len(nutrients)
            result.nutrients.extend(nutrients)

            # Emit stigmergy signal about nutrient-rich composting
            domain = chunk_data.get("heading", "unknown").split("/")[0].strip().lower()
            if nutrients:
                self.stigmergy.emit(PheromoneSignal(
                    signal_type=SignalType.NUTRIENT_RICH,
                    domain=domain or "unknown",
                    intensity=0.5,
                    source_component="composting",
                    source_id=chunk_id,
                ))

            # 5. Optionally archive original chunk
            if self.archive_after_composting:
                self.conn.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))

        result.cost_usd = self.llm.total_cost_usd
        return result

    def enrich_with_nutrients(self, new_content: str, limit: int = 3) -> str:
        """Search nutrients relevant to new_content and append as enrichment."""
        relevant = self.nutrient_store.search(new_content[:500], limit=limit)
        if not relevant:
            return new_content

        enrichment = "\n\n---\n**Composted Insights (from previous knowledge):**\n"
        for n in relevant:
            self.nutrient_store.increment_usage(n["id"])
            enrichment += f"\n- **[{n['nutrient_type']}]** {n['title']}: {n['content']}\n"

        return new_content + enrichment
