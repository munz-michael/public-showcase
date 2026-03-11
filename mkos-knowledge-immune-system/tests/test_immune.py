"""Tests for Knowledge Immune System module."""

from __future__ import annotations

import pytest

from tests.conftest import MockClaudeClient


def test_threat_types():
    """ThreatType enum should have all expected values."""
    from akm.immune.antigens import ThreatType

    assert ThreatType.HALLUCINATION.value == "hallucination"
    assert ThreatType.STALENESS.value == "staleness"
    assert ThreatType.BIAS.value == "bias"
    assert ThreatType.CONTRADICTION.value == "contradiction"


def test_immune_memory_record_and_match(seeded_db):
    """Immune memory should record and match patterns."""
    from akm.immune.antigens import Threat, ThreatType
    from akm.immune.memory import ImmuneMemory

    memory = ImmuneMemory(seeded_db)

    threat = Threat(
        threat_type=ThreatType.HALLUCINATION,
        target_id=1,
        target_type="chunk",
        confidence=0.8,
        description="Unsourced claim about performance",
        evidence="claimed 10x performance improvement",
    )

    pid = memory.record_detection(threat, detection_successful=True)
    assert pid > 0

    # Should match similar content
    match = memory.match_pattern("This shows 10x performance improvement", "hallucination")
    assert match is not None

    stats = memory.get_stats()
    assert stats["total_patterns"] == 1


def test_immune_memory_no_false_match(seeded_db):
    """Immune memory should not match unrelated content."""
    from akm.immune.antigens import Threat, ThreatType
    from akm.immune.memory import ImmuneMemory

    memory = ImmuneMemory(seeded_db)

    threat = Threat(
        threat_type=ThreatType.HALLUCINATION,
        target_id=1,
        target_type="chunk",
        confidence=0.8,
        description="Fake statistics",
        evidence="specific statistical fabrication",
    )
    memory.record_detection(threat, detection_successful=True)

    # Completely unrelated content should not match
    match = memory.match_pattern("The weather today is sunny", "hallucination")
    assert match is None


def test_clonal_selector_fitness(seeded_db):
    """Clonal selection should update fitness scores."""
    from akm.immune.clonal import ClonalSelector

    selector = ClonalSelector(seeded_db)

    # Insert a pattern
    seeded_db.execute(
        "INSERT INTO immune_patterns "
        "(pattern_type, pattern_signature, detection_strategy, fitness_score) "
        "VALUES (?, ?, ?, ?)",
        ("hallucination", "test|pattern", "test strategy", 0.5),
    )
    seeded_db.commit()

    # Positive feedback should boost
    new_score = selector.update_fitness(1, was_correct=True)
    assert new_score == pytest.approx(0.6)

    # Negative feedback should penalize
    new_score = selector.update_fitness(1, was_correct=False)
    assert new_score == pytest.approx(0.55)


def test_clonal_selector_prune(seeded_db):
    """Pruning should remove low-fitness patterns."""
    from akm.immune.clonal import ClonalSelector

    selector = ClonalSelector(seeded_db)

    # Insert patterns with varying fitness
    seeded_db.execute(
        "INSERT INTO immune_patterns "
        "(pattern_type, pattern_signature, detection_strategy, fitness_score, times_detected) "
        "VALUES (?, ?, ?, ?, ?)",
        ("hallucination", "good", "good strategy", 0.9, 10),
    )
    seeded_db.execute(
        "INSERT INTO immune_patterns "
        "(pattern_type, pattern_signature, detection_strategy, fitness_score, times_detected) "
        "VALUES (?, ?, ?, ?, ?)",
        ("hallucination", "bad", "bad strategy", 0.1, 10),
    )
    seeded_db.commit()

    result = selector.select_and_prune(min_fitness=0.2)
    assert result["pruned"] == 1
    assert result["total_after"] == 1


def test_immune_system_scan_chunk(seeded_db):
    """Full immune scan should detect threats."""
    from akm.immune.system import KnowledgeImmuneSystem

    # Mock LLM: 2-phase architecture
    # Phase 1: innate classification
    # Phase 2: deep analysis by specialized detector
    llm = MockClaudeClient(responses=[
        # Phase 1: innate says "staleness"
        {"label": "staleness", "confidence": 0.8, "reason": "Old version reference"},
        # Phase 2: StalenessDetector deep analysis
        [{"description": "Old version reference", "evidence": "Python 3.8", "confidence": 0.8}],
    ])

    system = KnowledgeImmuneSystem(seeded_db, llm)
    result = system.scan_chunk(1)

    assert result.target_id == 1
    assert len(result.threats_found) >= 1
    assert not result.is_healthy


def test_immune_system_healthy_chunk(seeded_db):
    """Clean content should pass immune scan."""
    from akm.immune.system import KnowledgeImmuneSystem

    # Mock LLM: innate says healthy (no Phase 2 needed)
    llm = MockClaudeClient(responses=[
        {"label": "healthy", "confidence": 0.9, "reason": "Accurate content"},
    ])

    system = KnowledgeImmuneSystem(seeded_db, llm)
    result = system.scan_chunk(5)  # "Unit tests should cover..." - benign content

    assert result.is_healthy


def test_immune_health_report(seeded_db):
    """Health report should return meaningful stats."""
    from akm.immune.system import KnowledgeImmuneSystem

    llm = MockClaudeClient(responses=[])
    system = KnowledgeImmuneSystem(seeded_db, llm)

    report = system.get_health_report()
    assert "total_chunks" in report
    assert report["total_chunks"] == 5
