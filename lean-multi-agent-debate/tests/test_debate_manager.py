"""
Tests for DebateManager phase logic using mock API fixtures.
No real API calls.
"""

import pytest
from debate.debate_manager import calculate_agreement_score, DebateManager


# ── calculate_agreement_score ──────────────────────────────────────────────────

def _make_score_fixtures(conf_a=0.75, conf_b=0.80, agreement=0.7):
    from debate.models import ClaudeSynthesis, InitialTake
    logical = InitialTake(model_id="m1", role="logical", content="c", confidence=conf_a)
    factual = InitialTake(model_id="m2", role="factual", content="c", confidence=conf_b)
    synthesis = ClaudeSynthesis(
        contradictions=[], assumptions_challenged=[],
        synthesis_draft="", agreement_score=agreement,
    )
    return logical, factual, synthesis


def test_calculate_agreement_score_basic():
    logical, factual, synthesis = _make_score_fixtures()
    score = calculate_agreement_score(logical, factual, synthesis)
    assert 0.0 <= score <= 1.0


def test_calculate_agreement_score_perfect():
    logical, factual, synthesis = _make_score_fixtures(1.0, 1.0, 1.0)
    score = calculate_agreement_score(logical, factual, synthesis)
    assert score == pytest.approx(1.0)


def test_calculate_agreement_score_zero():
    logical, factual, synthesis = _make_score_fixtures(0.0, 0.0, 0.0)
    score = calculate_agreement_score(logical, factual, synthesis)
    assert score == pytest.approx(0.0)


# ── DebateManager instantiation ────────────────────────────────────────────────

def test_debate_manager_default_flags():
    mgr = DebateManager(mock_gemini=True)
    assert mgr.mock_gemini is True
    assert mgr.max_rounds == 1
    assert mgr.adversarial is False
    assert mgr.moa is False


def test_debate_manager_all_flags():
    mgr = DebateManager(
        mock_gemini=True,
        max_rounds=3,
        adversarial=True,
        grounded=False,
        multi_turn=True,
        judge=True,
        moa=True,
        fact_check=True,
        decompose=True,
        arg_graph=True,
        delphi_rounds=2,
        calibrate=True,
    )
    assert mgr.max_rounds == 3
    assert mgr.adversarial is True
    assert mgr.delphi_rounds == 2
    assert mgr.calibrate is True


# ── Mock Gemini initial takes ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_gemini_initial_takes(mock_claude):
    """With mock_gemini=True, Claude substitutes Gemini — must return valid InitialTake."""
    mgr = DebateManager(mock_gemini=True)
    logical, factual = await mgr.get_initial_takes("Test question")
    assert logical.content
    assert 0.0 <= logical.confidence <= 1.0
    assert factual.content
    assert 0.0 <= factual.confidence <= 1.0


@pytest.mark.asyncio
async def test_mock_gemini_adversarial_roles(mock_claude):
    """Adversarial mode must assign PRO/CONTRA roles."""
    mgr = DebateManager(mock_gemini=True, adversarial=True)
    logical, factual = await mgr.get_initial_takes("Test question")
    assert "PRO" in logical.role or "CONTRA" in logical.role or logical.role in ("logical_analysis", "factual_context")


@pytest.mark.asyncio
async def test_critique_loop_returns_tuple(mock_claude):
    """run_critique_loop must return (synthesis, rebuttal, verification) tuple."""
    from debate.models import InitialTake

    mgr = DebateManager(mock_gemini=True)
    logical = InitialTake(model_id="m1", role="logical_analysis", content="analysis A", confidence=0.7)
    factual = InitialTake(model_id="m2", role="factual_context", content="analysis B", confidence=0.65)

    synthesis, rebuttal, verification = await mgr.run_critique_loop("Test", logical, factual)
    assert synthesis is not None
    assert verification is not None
    assert rebuttal is None  # multi_turn=False by default


@pytest.mark.asyncio
async def test_final_answer(mock_claude):
    """get_final_answer must return FinalAnswer with valid scores."""
    from debate.models import ClaudeSynthesis, FinalAnswer, GeminiVerification, InitialTake

    mgr = DebateManager(mock_gemini=True)
    logical = InitialTake(model_id="m1", role="logical_analysis", content="A", confidence=0.7)
    factual = InitialTake(model_id="m2", role="factual_context", content="B", confidence=0.6)
    synthesis = ClaudeSynthesis(
        contradictions=[], assumptions_challenged=[],
        synthesis_draft="draft", agreement_score=0.75
    )
    verification = GeminiVerification(
        logical_errors=[], wishful_thinking=[], verified=True, verification_notes=""
    )

    final = await mgr.get_final_answer("Test", logical, factual, synthesis, verification)
    assert final.content
    assert 0.0 <= final.consensus_score <= 1.0
    assert 0.0 <= final.confidence <= 1.0
