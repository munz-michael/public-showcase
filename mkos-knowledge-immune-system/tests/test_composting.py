"""Tests for Knowledge Composting module."""

from __future__ import annotations

from tests.conftest import MockClaudeClient


def test_entropy_scorer_age_based(seeded_db):
    """Entropy should be near 0 for fresh chunks."""
    from akm.composting.entropy import EntropyScorer

    scorer = EntropyScorer(seeded_db)
    score = scorer.compute_age_entropy(1)
    # Just created, so should be very low
    assert 0.0 <= score < 0.1


def test_entropy_scorer_score_chunk(seeded_db):
    """Score a chunk and persist result."""
    from akm.composting.entropy import EntropyScorer

    scorer = EntropyScorer(seeded_db)
    score = scorer.score_chunk(1)
    assert 0.0 <= score <= 1.0

    # Verify persisted
    row = seeded_db.execute(
        "SELECT entropy_score FROM chunk_entropy WHERE chunk_id = 1"
    ).fetchone()
    assert row is not None
    assert row["entropy_score"] == score


def test_entropy_scorer_get_compostable(seeded_db):
    """Chunks with high entropy should be returned."""
    from akm.composting.entropy import EntropyScorer

    scorer = EntropyScorer(seeded_db)
    # Manually insert high entropy
    seeded_db.execute(
        "INSERT INTO chunk_entropy (chunk_id, entropy_score, validation_source) "
        "VALUES (1, 0.9, 'test')"
    )
    seeded_db.execute(
        "INSERT INTO chunk_entropy (chunk_id, entropy_score, validation_source) "
        "VALUES (2, 0.3, 'test')"
    )

    compostable = scorer.get_compostable(threshold=0.7)
    assert len(compostable) == 1
    assert compostable[0]["chunk_id"] == 1


def test_decomposer(seeded_db):
    """Decomposer should extract nutrients from content."""
    from akm.composting.decomposer import KnowledgeDecomposer

    llm = MockClaudeClient(responses=[
        [
            {"type": "principle", "title": "Version Independence", "content": "Core language features outlast specific versions", "confidence": 0.8},
            {"type": "error_pattern", "title": "Version Pinning", "content": "Referencing specific versions makes content stale quickly", "confidence": 0.9},
        ]
    ])

    decomposer = KnowledgeDecomposer(llm)
    nutrients = decomposer.decompose("Python 3.8 was released in 2019 with walrus operator.")

    assert len(nutrients) == 2
    assert nutrients[0].nutrient_type == "principle"
    assert nutrients[0].title == "Version Independence"
    assert nutrients[1].nutrient_type == "error_pattern"


def test_nutrient_store_crud(seeded_db):
    """NutrientStore should insert and search nutrients."""
    from akm.composting.decomposer import Nutrient
    from akm.composting.nutrient_store import NutrientStore

    store = NutrientStore(seeded_db)

    nutrient = Nutrient(
        nutrient_type="principle",
        title="Abstraction over implementation",
        content="Focus on interfaces, not specific implementations",
        confidence=0.85,
    )
    nid = store.insert(nutrient, source_chunk_id=1, source_document_id=1)
    assert nid > 0

    # Search
    results = store.search("interfaces implementation")
    assert len(results) >= 1
    assert results[0]["title"] == "Abstraction over implementation"

    # Stats
    stats = store.get_stats()
    assert stats["total"] == 1


def test_composter_dry_run(seeded_db):
    """Composter dry-run should score chunks but not decompose."""
    from akm.composting.composter import KnowledgeComposter

    # Mock LLM returns high entropy for first 3 chunks, low for last 2
    llm = MockClaudeClient(responses=[
        {"entropy": 0.95, "reason": "outdated"},
        {"entropy": 0.95, "reason": "outdated"},
        {"entropy": 0.95, "reason": "outdated"},
        {"entropy": 0.1, "reason": "current"},
        {"entropy": 0.1, "reason": "current"},
    ])

    # Threshold 0.5: combined = 0.4*~0 + 0.6*0.95 = 0.57 > 0.5 ✓
    composter = KnowledgeComposter(seeded_db, llm, entropy_threshold=0.5)
    result = composter.run(dry_run=True)

    assert result.chunks_scored == 5  # all chunks scored
    assert result.chunks_composted == 3  # 3 above threshold
    assert result.nutrients_extracted == 0  # dry run, no extraction


def test_composter_enrich_with_nutrients(seeded_db):
    """Enrichment should append relevant nutrients to new content."""
    from akm.composting.composter import KnowledgeComposter
    from akm.composting.decomposer import Nutrient
    from akm.composting.nutrient_store import NutrientStore

    llm = MockClaudeClient()
    store = NutrientStore(seeded_db)
    store.insert(
        Nutrient("principle", "API Stability", "APIs should be versioned for stability", 0.9),
        source_chunk_id=1,
        source_document_id=1,
    )

    composter = KnowledgeComposter(seeded_db, llm)
    enriched = composter.enrich_with_nutrients("How should we design our API?")

    assert "Composted Insights" in enriched
    assert "API Stability" in enriched
