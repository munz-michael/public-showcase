"""Tests for Knowledge Fermentation module."""

from __future__ import annotations

from tests.conftest import MockClaudeClient


def test_chamber_ingest(seeded_db):
    """Chamber should accept new content."""
    from akm.fermentation.chamber import FermentationChamber

    chamber = FermentationChamber(seeded_db)
    fid = chamber.ingest("New knowledge about AI agents", title="AI Agents", duration_hours=12)
    assert fid > 0

    item = chamber.get_by_id(fid)
    assert item is not None
    assert item.status == "fermenting"
    assert item.title == "AI Agents"
    assert item.fermentation_duration_hours == 12


def test_chamber_get_fermenting(seeded_db):
    """Should list fermenting items."""
    from akm.fermentation.chamber import FermentationChamber

    chamber = FermentationChamber(seeded_db)
    chamber.ingest("Content 1", title="Item 1")
    chamber.ingest("Content 2", title="Item 2")

    items = chamber.get_fermenting()
    assert len(items) == 2


def test_chamber_promote_reject(seeded_db):
    """Promote and reject should update status."""
    from akm.fermentation.chamber import FermentationChamber

    chamber = FermentationChamber(seeded_db)
    fid1 = chamber.ingest("Good content")
    fid2 = chamber.ingest("Bad content")

    chamber.promote(fid1)
    chamber.reject(fid2, "Too many contradictions")

    item1 = chamber.get_by_id(fid1)
    item2 = chamber.get_by_id(fid2)
    assert item1.status == "promoted"
    assert item2.status == "rejected"


def test_cross_referencing(seeded_db):
    """Cross-referencing should find related chunks."""
    from akm.fermentation.chamber import FermentationChamber
    from akm.fermentation.cross_ref import CrossReferencer

    llm = MockClaudeClient(responses=[
        {"relationship": "extends", "similarity": 0.7, "explanation": "Extends existing info"},
    ])

    chamber = FermentationChamber(seeded_db)
    fid = chamber.ingest("Python 3.12 introduces new type parameter syntax")

    cross_ref = CrossReferencer(seeded_db, llm)
    refs = cross_ref.find_references(fid)

    # Should find related Python chunks
    assert isinstance(refs, list)


def test_contradiction_detection(seeded_db):
    """Contradiction detector should identify conflicts."""
    from akm.fermentation.contradiction import ContradictionDetector

    llm = MockClaudeClient(responses=[
        [{"new_excerpt": "Use let/const", "existing_chunk_id": 3,
          "existing_excerpt": "Always use var", "severity": "major",
          "explanation": "Modern JS uses let/const", "suggested_resolution": "Update to modern practice"}]
    ])

    detector = ContradictionDetector(llm)
    chunks = [{"id": 3, "heading": "Best Practices",
               "content": "Always use var in JavaScript for variable declarations."}]

    contradictions = detector.detect("Always use let and const in JavaScript.", chunks)
    assert len(contradictions) == 1
    assert contradictions[0].severity == "major"


def test_fermenter_immediate_integrate(seeded_db):
    """Immediate integration should skip fermentation."""
    from akm.fermentation.fermenter import Fermenter

    llm = MockClaudeClient()
    fermenter = Fermenter(seeded_db, llm, duration_hours=24)

    result = fermenter.immediate_integrate("Quick content", title="Quick")
    assert result.status == "promoted"
    assert result.final_confidence == 1.0


def test_fermenter_confidence_computation(seeded_db):
    """Confidence should decrease with contradictions."""
    from akm.fermentation.fermenter import Fermenter, FermentationResult
    from akm.fermentation.contradiction import Contradiction

    llm = MockClaudeClient()
    fermenter = Fermenter(seeded_db, llm)

    # No contradictions
    r1 = FermentationResult(cross_refs_found=3, contradictions_found=0)
    c1 = fermenter._compute_confidence(r1)

    # With critical contradiction
    r2 = FermentationResult(
        cross_refs_found=3,
        contradictions_found=1,
        contradictions=[Contradiction("a", 1, "b", "critical", "conflict", "fix")],
    )
    c2 = fermenter._compute_confidence(r2)

    assert c1 > c2  # Contradictions should lower confidence
