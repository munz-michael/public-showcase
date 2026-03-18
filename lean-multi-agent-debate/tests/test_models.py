"""
Tests for Pydantic v2 models — validation, clamping, computed properties.
No API calls required.
"""

import pytest
from debate.models import (
    ArgumentEdge,
    ArgumentGraph,
    ArgumentNode,
    AtomicClaim,
    CalibrationRecord,
    ClaudeSynthesis,
    ConfidenceClaim,
    Contradiction,
    DebateResult,
    DelphiProcess,
    DelphiRound,
    FactCheckResult,
    FinalAnswer,
    GeminiRebuttal,
    GeminiVerification,
    InitialTake,
    JudgeVerdict,
    ProblemDecomposition,
    RubricScore,
    SubQuestion,
)


# ── InitialTake ────────────────────────────────────────────────────────────────

def test_initial_take_confidence_clamp_high():
    take = InitialTake(model_id="m", role="r", content="c", confidence=1.5)
    assert take.confidence == 1.0


def test_initial_take_confidence_clamp_low():
    take = InitialTake(model_id="m", role="r", content="c", confidence=-0.3)
    assert take.confidence == 0.0


def test_initial_take_confidence_valid():
    take = InitialTake(model_id="m", role="r", content="c", confidence=0.75)
    assert take.confidence == 0.75


def test_initial_take_defaults():
    take = InitialTake(model_id="m", role="r", content="c", confidence=0.5)
    assert take.known_unknowns == []
    assert take.sources == []
    assert take.aggregated_from == []


# ── RubricScore ────────────────────────────────────────────────────────────────

def test_rubric_score_clamp():
    r = RubricScore(logical_coherence=10, evidence_quality=0, completeness=3, reasoning_depth=3)
    assert r.logical_coherence == 5
    assert r.evidence_quality == 1


def test_rubric_score_normalized():
    r = RubricScore(logical_coherence=4, evidence_quality=4, completeness=4, reasoning_depth=4)
    assert r.normalized == pytest.approx(0.8)


def test_rubric_score_normalized_max():
    r = RubricScore(logical_coherence=5, evidence_quality=5, completeness=5, reasoning_depth=5)
    assert r.normalized == pytest.approx(1.0)


# ── FactCheckResult ────────────────────────────────────────────────────────────

def test_fact_check_counts():
    fc = FactCheckResult(
        claims=[
            AtomicClaim(claim="A", source_role="r", status="confirmed", evidence="e", confidence=0.9),
            AtomicClaim(claim="B", source_role="r", status="refuted", evidence="e", confidence=0.8),
            AtomicClaim(claim="C", source_role="r", status="uncertain", evidence="e", confidence=0.5),
            AtomicClaim(claim="D", source_role="r", status="confirmed", evidence="e", confidence=0.7),
        ],
        overall_reliability=0.75,
        summary="Mixed results",
    )
    assert fc.confirmed_count == 2
    assert fc.refuted_count == 1
    assert fc.uncertain_count == 1


def test_fact_check_reliability_clamp():
    fc = FactCheckResult(claims=[], overall_reliability=1.5, summary="")
    assert fc.overall_reliability == 1.0


# ── DelphiRound ────────────────────────────────────────────────────────────────

def test_delphi_round_delta_clamp():
    r = DelphiRound(
        round_n=1, position_a="a", position_b="b",
        confidence_a=2.0, confidence_b=-0.1,
        consensus_summary="x", delta=1.5
    )
    assert r.confidence_a == 1.0
    assert r.confidence_b == 0.0
    assert r.delta == 1.0


def test_delphi_process_converged():
    dp = DelphiProcess(
        rounds=[
            DelphiRound(round_n=1, position_a="a", position_b="b",
                        confidence_a=0.5, confidence_b=0.6, consensus_summary="x", delta=0.0),
            DelphiRound(round_n=2, position_a="a", position_b="b",
                        confidence_a=0.55, confidence_b=0.62, consensus_summary="x", delta=0.03),
        ],
        converged=True,
        convergence_round=2,
    )
    assert dp.converged is True
    assert dp.convergence_round == 2


# ── ArgumentGraph ──────────────────────────────────────────────────────────────

def test_argument_graph_contradiction_edges():
    graph = ArgumentGraph(
        nodes=[
            ArgumentNode(id="A1", node_type="premise", content="x", source_role="r"),
            ArgumentNode(id="B1", node_type="premise", content="y", source_role="r"),
        ],
        edges=[
            ArgumentEdge(from_id="A1", to_id="B1", edge_type="contradicts"),
            ArgumentEdge(from_id="A1", to_id="B1", edge_type="supports"),
        ],
        summary="test",
    )
    assert len(graph.contradiction_edges) == 1


def test_argument_graph_to_mermaid():
    graph = ArgumentGraph(
        nodes=[ArgumentNode(id="A1", node_type="premise", content="test", source_role="logical")],
        edges=[],
        summary="",
    )
    mermaid = graph.to_mermaid()
    assert "flowchart LR" in mermaid
    assert "A1" in mermaid


# ── DebateResult serialization ─────────────────────────────────────────────────

def test_debate_result_serialization():
    result = DebateResult(
        problem="Test problem",
        logical_analysis=InitialTake(model_id="m1", role="logical", content="c1", confidence=0.7),
        factual_context=InitialTake(model_id="m2", role="factual", content="c2", confidence=0.6),
        critique=ClaudeSynthesis(
            contradictions=[],
            assumptions_challenged=[],
            synthesis_draft="draft",
            agreement_score=0.75,
        ),
        verification=GeminiVerification(
            logical_errors=[], wishful_thinking=[], verified=True, verification_notes=""
        ),
        final_answer=FinalAnswer(
            content="final", key_disagreements=[], consensus_score=0.8, confidence=0.85
        ),
    )
    data = result.model_dump()
    assert data["problem"] == "Test problem"
    assert data["final_answer"]["consensus_score"] == pytest.approx(0.8)
    assert data["decomposition"] is None
    assert data["fact_check"] is None
