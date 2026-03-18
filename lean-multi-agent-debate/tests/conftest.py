"""
Shared fixtures for the debate engine test suite.
Mock Claude + Mock Gemini — no real API calls.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Canned API responses ───────────────────────────────────────────────────────

CANNED_INITIAL_TAKE = json.dumps({
    "content": "This is a test analysis.",
    "chain_of_thought": "Step 1: think. Step 2: conclude.",
    "confidence": 0.75,
    "known_unknowns": ["Uncertainty A"],
    "sources": [],
    "aggregated_from": [],
})

CANNED_CRITIQUE = json.dumps({
    "contradictions": [
        {"claim_a": "A says yes", "claim_b": "B says no", "severity": "minor"}
    ],
    "assumptions_challenged": ["Assumes stable context"],
    "synthesis_draft": "Both analyses broadly agree.",
    "agreement_score": 0.72,
    "rubric_logical": {
        "logical_coherence": 4, "evidence_quality": 3,
        "completeness": 3, "reasoning_depth": 4,
    },
    "rubric_factual": {
        "logical_coherence": 3, "evidence_quality": 4,
        "completeness": 4, "reasoning_depth": 3,
    },
})

CANNED_VERIFICATION = json.dumps({
    "logical_errors": [],
    "wishful_thinking": [],
    "verified": True,
    "verification_notes": "No issues found.",
})

CANNED_FINAL = json.dumps({
    "content": "The final answer is: it depends.",
    "key_disagreements": [],
    "consensus_score": 0.78,
    "confidence": 0.80,
})

CANNED_DECOMPOSITION = json.dumps({
    "sub_questions": [
        {"question": "What is the technical risk?", "aspect": "technical"},
        {"question": "What is the economic impact?", "aspect": "economic"},
    ],
    "reasoning": "The problem has multiple dimensions.",
    "complexity": "moderate",
})

CANNED_FACT_CHECK = json.dumps({
    "claims": [
        {
            "claim": "RSA-2048 is widely used.",
            "source_role": "logical_analysis",
            "status": "confirmed",
            "evidence": "NIST standards confirm this.",
            "confidence": 0.95,
        }
    ],
    "overall_reliability": 0.9,
    "summary": "Most claims are confirmed.",
})

CANNED_CALIBRATION = json.dumps({
    "claims": [
        {
            "claim": "There is a 30% chance of X in 5 years.",
            "probability": 0.30,
            "ci_lower": 0.15,
            "ci_upper": 0.50,
            "model_id": "claude-opus-4-6",
            "source_role": "logical_analysis",
            "time_horizon": "5 years",
        }
    ]
})

CANNED_ARGUMENT_GRAPH = json.dumps({
    "nodes": [
        {"id": "A1", "node_type": "premise", "content": "Quantum computers exist.", "source_role": "logical_analysis"},
        {"id": "B1", "node_type": "evidence", "content": "RSA is vulnerable.", "source_role": "factual_context"},
        {"id": "C1", "node_type": "conclusion", "content": "RSA needs replacement.", "source_role": "logical_analysis"},
    ],
    "edges": [
        {"from_id": "A1", "to_id": "C1", "edge_type": "supports", "label": ""},
        {"from_id": "B1", "to_id": "C1", "edge_type": "derives", "label": ""},
    ],
    "summary": "Both analyses point toward RSA being at risk.",
})

CANNED_DELPHI_ROUND = json.dumps({
    "position_a": "Moderate risk.",
    "position_b": "High risk.",
    "confidence_a": 0.65,
    "confidence_b": 0.80,
    "consensus_summary": "Experts see elevated risk.",
    "delta": 0.08,
})


# ── Mock Claude fixture ────────────────────────────────────────────────────────

def _make_claude_message(text: str):
    """Build a minimal Anthropic Message-like object."""
    content_block = MagicMock()
    content_block.type = "text"
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@pytest.fixture
def mock_claude(monkeypatch):
    """
    Patches anthropic.AsyncAnthropic so all claude messages return
    canned JSON based on which 'phase' is being called.
    """
    async def _fake_create(*args, **kwargs):
        messages = kwargs.get("messages", [])
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )

        # Route to the correct canned response based on prompt keywords
        if "decompose" in last_user.lower() or "sub-question" in last_user.lower():
            text = CANNED_DECOMPOSITION
        elif "fact-check" in last_user.lower() or "atomic claim" in last_user.lower():
            text = CANNED_FACT_CHECK
        elif "argument graph" in last_user.lower() or "argumentnode" in last_user.lower():
            text = CANNED_ARGUMENT_GRAPH
        elif "calibration" in last_user.lower() or "probabilistic" in last_user.lower():
            text = CANNED_CALIBRATION
        elif "critique" in last_user.lower() or "contradiction" in last_user.lower():
            text = CANNED_CRITIQUE
        elif "final" in last_user.lower() or "consensus" in last_user.lower():
            text = CANNED_FINAL
        elif "delphi" in last_user.lower():
            text = CANNED_DELPHI_ROUND
        else:
            text = CANNED_INITIAL_TAKE

        return _make_claude_message(text)

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=_fake_create)

    with patch("debate.debate_manager._claude", mock_client):
        yield mock_client


# ── Mock Gemini fixture ────────────────────────────────────────────────────────

@pytest.fixture
def mock_gemini_api(monkeypatch):
    """
    Patches Gemini genai.Client so all calls return canned InitialTake JSON.
    The debate engine already has --mock-gemini that substitutes Claude; this
    fixture patches at the genai level for lower-level tests.
    """
    fake_response = MagicMock()
    fake_response.text = CANNED_INITIAL_TAKE

    fake_client = MagicMock()
    fake_client.models = MagicMock()
    fake_client.models.generate_content = MagicMock(return_value=fake_response)

    with patch("debate.debate_manager._gemini_client", fake_client):
        yield fake_client
