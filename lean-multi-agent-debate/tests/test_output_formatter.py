"""
Smoke tests for OutputFormatter — verify rendering doesn't raise exceptions.
No API calls required.
"""

import pytest
from io import StringIO
from rich.console import Console

from debate.models import (
    ArgumentEdge,
    ArgumentGraph,
    ArgumentNode,
    ClaudeSynthesis,
    Contradiction,
    FinalAnswer,
    GeminiVerification,
    InitialTake,
    ProblemDecomposition,
    RubricScore,
    SubQuestion,
)
from debate.output_formatter import OutputFormatter


@pytest.fixture
def fmt():
    return OutputFormatter()


@pytest.fixture
def logical():
    return InitialTake(model_id="gemini-thinking", role="logical_analysis", content="Logic analysis.", confidence=0.75)


@pytest.fixture
def factual():
    return InitialTake(model_id="gemini-pro", role="factual_context", content="Factual context.", confidence=0.65)


@pytest.fixture
def synthesis():
    return ClaudeSynthesis(
        contradictions=[Contradiction(claim_a="A says yes", claim_b="B says no", severity="minor")],
        assumptions_challenged=["Assumes X"],
        synthesis_draft="Synthesis text.",
        agreement_score=0.72,
        rubric_logical=RubricScore(),
        rubric_factual=RubricScore(),
    )


@pytest.fixture
def verification():
    return GeminiVerification(
        logical_errors=[], wishful_thinking=[], verified=True, verification_notes="All good."
    )


@pytest.fixture
def final():
    return FinalAnswer(
        content="Final answer.", key_disagreements=[], consensus_score=0.78, confidence=0.82
    )


# ── Smoke tests ────────────────────────────────────────────────────────────────

def test_print_header_no_crash(fmt):
    fmt.print_header("Is quantum computing a threat to RSA-2048?")


def test_print_phase1_no_crash(fmt, logical, factual):
    fmt.print_phase1(logical, factual)


def test_print_contradictions_no_crash(fmt, synthesis):
    fmt.print_contradictions(synthesis.contradictions)


def test_print_contradictions_empty_no_crash(fmt):
    fmt.print_contradictions([])


def test_print_critique_no_crash(fmt, synthesis, verification):
    fmt.print_critique(synthesis, verification)


def test_print_final_no_crash(fmt, final):
    fmt.print_final(final)


def test_print_decomposition_no_crash(fmt):
    decomp = ProblemDecomposition(
        sub_questions=[
            SubQuestion(question="What is the technical risk?", aspect="technical"),
            SubQuestion(question="What is the timeline?", aspect="empirical"),
        ],
        reasoning="Multi-faceted problem.",
        complexity="moderate",
    )
    fmt.print_decomposition(decomp)


# ── Argument graph DOT format ──────────────────────────────────────────────────

def test_argument_graph_mermaid_contains_nodes():
    graph = ArgumentGraph(
        nodes=[
            ArgumentNode(id="A1", node_type="premise", content="Quantum computers exist.", source_role="logical"),
            ArgumentNode(id="B1", node_type="conclusion", content="RSA is at risk.", source_role="factual"),
        ],
        edges=[
            ArgumentEdge(from_id="A1", to_id="B1", edge_type="supports"),
        ],
        summary="Summary",
    )
    mermaid = graph.to_mermaid()
    assert "A1" in mermaid
    assert "B1" in mermaid
    assert "flowchart LR" in mermaid
    assert "supports" in mermaid or "-->" in mermaid


def test_argument_graph_mermaid_contradiction_style():
    graph = ArgumentGraph(
        nodes=[
            ArgumentNode(id="A1", node_type="premise", content="A", source_role="r"),
            ArgumentNode(id="B1", node_type="premise", content="B", source_role="r"),
        ],
        edges=[ArgumentEdge(from_id="A1", to_id="B1", edge_type="contradicts")],
        summary="",
    )
    mermaid = graph.to_mermaid()
    assert "contradicts" in mermaid
    assert "-.-" in mermaid  # dashed line for contradictions
