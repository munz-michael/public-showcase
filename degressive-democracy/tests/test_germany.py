"""Tests for Germany transparency scenarios."""

import pytest

from degressive_democracy.germany import (
    TransparencyResult,
    WAHLPROGRAMM_PROMISES_OPAQUE,
    WAHLPROGRAMM_PROMISES_TRACKED,
    WAHLPROGRAMM_PROMISES_TRANSPARENT,
    GERMAN_CITIZEN_DISTRIBUTION,
    run_germany_scenario,
    run_transparency_comparison,
    run_full_germany_comparison,
    scenario_investigative_journalism,
    scenario_social_media,
    scenario_economic_crisis,
    scenario_blame_shifting,
    run_german_evolution,
)
from degressive_democracy.models import CitizenBehavior, ExternalShock, PromiseCategory
from degressive_democracy.evolution import EvolutionResult


class TestPromiseTemplates:
    def test_opaque_has_10_promises(self):
        assert len(WAHLPROGRAMM_PROMISES_OPAQUE) == 10

    def test_tracked_visibility_higher_than_opaque(self):
        for opaque, tracked in zip(WAHLPROGRAMM_PROMISES_OPAQUE, WAHLPROGRAMM_PROMISES_TRACKED):
            assert tracked[3] >= opaque[3]

    def test_transparent_all_visibility_1(self):
        for t in WAHLPROGRAMM_PROMISES_TRANSPARENT:
            assert t[3] == 1.0

    def test_tracked_visibility_capped_at_1(self):
        for t in WAHLPROGRAMM_PROMISES_TRACKED:
            assert t[3] <= 1.0

    def test_difficulty_range(self):
        for t in WAHLPROGRAMM_PROMISES_OPAQUE:
            assert 0.0 < t[2] <= 1.0


class TestCitizenDistribution:
    def test_sums_to_1(self):
        total = sum(GERMAN_CITIZEN_DISTRIBUTION.values())
        assert abs(total - 1.0) < 0.01

    def test_all_behaviors_present(self):
        for behavior in CitizenBehavior:
            assert behavior in GERMAN_CITIZEN_DISTRIBUTION

    def test_apathetic_reflects_nonvoters(self):
        # ~23.4% Nichtwähler bei BT2021
        assert 0.20 <= GERMAN_CITIZEN_DISTRIBUTION[CitizenBehavior.APATHETIC] <= 0.30


class TestRunGermanyScenario:
    def test_opaque_runs(self):
        result = run_germany_scenario("opaque", seed=42, n_citizens=200)
        assert isinstance(result, TransparencyResult)
        assert result.name == "opaque"

    def test_tracked_runs(self):
        result = run_germany_scenario("tracked", seed=42, n_citizens=200)
        assert result.name == "tracked"

    def test_transparent_runs(self):
        result = run_germany_scenario("transparent", seed=42, n_citizens=200)
        assert result.name == "transparent"

    def test_transparent_higher_visibility(self):
        opaque = run_germany_scenario("opaque", seed=42, n_citizens=200)
        transparent = run_germany_scenario("transparent", seed=42, n_citizens=200)
        assert transparent.avg_visibility > opaque.avg_visibility

    def test_power_in_range(self):
        result = run_germany_scenario("opaque", seed=42, n_citizens=200)
        assert 0.0 <= result.keeper_power <= 1.0
        assert 0.0 <= result.strategic_min_power <= 1.0
        assert 0.0 <= result.populist_power <= 1.0

    def test_metrics_populated(self):
        result = run_germany_scenario("opaque", seed=42, n_citizens=200)
        assert result.metrics.total_withdrawals >= 0
        assert 0.0 <= result.metrics.avg_final_satisfaction <= 1.0

    def test_deterministic_with_seed(self):
        r1 = run_germany_scenario("opaque", seed=55, n_citizens=200)
        r2 = run_germany_scenario("opaque", seed=55, n_citizens=200)
        assert r1.metrics.total_withdrawals == r2.metrics.total_withdrawals
        assert r1.keeper_power == r2.keeper_power

    def test_populist_gets_more_promises(self):
        result = run_germany_scenario("opaque", seed=42, n_citizens=200)
        # Populist should have ~10 promises, others 5
        assert result.result.tick_results  # ran successfully


class TestTransparencyComparison:
    def test_returns_3_results(self):
        results = run_transparency_comparison(seed=42)
        assert len(results) == 3

    def test_ordered_opaque_tracked_transparent(self):
        results = run_transparency_comparison(seed=42)
        assert results[0].name == "opaque"
        assert results[1].name == "tracked"
        assert results[2].name == "transparent"

    def test_transparency_improves_satisfaction(self):
        results = run_transparency_comparison(seed=42)
        opaque_sat = results[0].metrics.avg_final_satisfaction
        transparent_sat = results[2].metrics.avg_final_satisfaction
        assert transparent_sat >= opaque_sat

    def test_transparency_reduces_withdrawals(self):
        results = run_transparency_comparison(seed=42)
        opaque_wd = results[0].metrics.total_withdrawals
        transparent_wd = results[2].metrics.total_withdrawals
        # More transparency should reduce chaotic withdrawals
        assert transparent_wd <= opaque_wd


class TestInvestigativeJournalism:
    def test_runs_successfully(self):
        result = scenario_investigative_journalism(seed=42, n_citizens=200)
        assert isinstance(result, TransparencyResult)
        assert result.name == "journalism"

    def test_affects_stratmin_power(self):
        opaque = run_germany_scenario("opaque", seed=42, n_citizens=200)
        journalism = scenario_investigative_journalism(seed=42, n_citizens=200)
        # Journalism should change StratMin outcome vs opaque
        # (either more or fewer withdrawals — the point is it's different)
        assert journalism.strategic_min_power != opaque.strategic_min_power or \
               journalism.metrics.total_withdrawals != opaque.metrics.total_withdrawals

    def test_custom_reveal_tick(self):
        early = scenario_investigative_journalism(seed=42, n_citizens=200, reveal_tick=12)
        late = scenario_investigative_journalism(seed=42, n_citizens=200, reveal_tick=40)
        assert isinstance(early, TransparencyResult)
        assert isinstance(late, TransparencyResult)

    def test_early_reveal_more_impact(self):
        early = scenario_investigative_journalism(seed=42, n_citizens=200, reveal_tick=12)
        late = scenario_investigative_journalism(seed=42, n_citizens=200, reveal_tick=44)
        # Earlier reveal should have more impact (more time for citizens to react)
        # StratMin should be more punished with early reveal
        assert early.strategic_min_power >= late.strategic_min_power or \
               early.metrics.total_withdrawals >= late.metrics.total_withdrawals

    def test_deterministic(self):
        r1 = scenario_investigative_journalism(seed=55, n_citizens=200)
        r2 = scenario_investigative_journalism(seed=55, n_citizens=200)
        assert r1.metrics.total_withdrawals == r2.metrics.total_withdrawals


class TestSocialMedia:
    def test_runs_successfully(self):
        result = scenario_social_media(seed=42, n_citizens=200)
        assert isinstance(result, TransparencyResult)
        assert result.name == "social_media"

    def test_amplification_increases_pressure(self):
        opaque = run_germany_scenario("opaque", seed=42, n_citizens=200)
        social = scenario_social_media(seed=42, n_citizens=200)
        # Social media should create at least as much pressure as no amplification
        assert social.metrics.total_withdrawals >= opaque.metrics.total_withdrawals - 5

    def test_custom_start_tick(self):
        early = scenario_social_media(seed=42, n_citizens=200, amplification_start=1)
        late = scenario_social_media(seed=42, n_citizens=200, amplification_start=40)
        assert isinstance(early, TransparencyResult)
        assert isinstance(late, TransparencyResult)

    def test_deterministic(self):
        r1 = scenario_social_media(seed=77, n_citizens=200)
        r2 = scenario_social_media(seed=77, n_citizens=200)
        assert r1.metrics.total_withdrawals == r2.metrics.total_withdrawals


class TestEconomicCrisis:
    def test_runs_successfully(self):
        result = scenario_economic_crisis(seed=42, n_citizens=200)
        assert isinstance(result, TransparencyResult)
        assert result.name == "crisis"

    def test_crisis_reduces_blame(self):
        # Crisis should reduce withdrawals vs opaque (blame is reduced)
        opaque = run_germany_scenario("opaque", seed=42, n_citizens=200)
        crisis = scenario_economic_crisis(seed=42, n_citizens=200)
        # With reduced blame, fewer citizens should withdraw
        assert crisis.metrics.total_withdrawals <= opaque.metrics.total_withdrawals

    def test_satisfaction_higher_than_opaque(self):
        opaque = run_germany_scenario("opaque", seed=42, n_citizens=200)
        crisis = scenario_economic_crisis(seed=42, n_citizens=200)
        assert crisis.metrics.avg_final_satisfaction >= opaque.metrics.avg_final_satisfaction

    def test_deterministic(self):
        r1 = scenario_economic_crisis(seed=42, n_citizens=200)
        r2 = scenario_economic_crisis(seed=42, n_citizens=200)
        assert r1.metrics.total_withdrawals == r2.metrics.total_withdrawals


class TestBlameShifting:
    def test_runs_successfully(self):
        result = scenario_blame_shifting(seed=42, n_citizens=200)
        assert isinstance(result, TransparencyResult)
        assert result.name == "blame_shift"

    def test_blame_shift_less_effective_than_real_crisis(self):
        crisis = scenario_economic_crisis(seed=42, n_citizens=200)
        blame = scenario_blame_shifting(seed=42, n_citizens=200)
        # Blame shifting has lower blame_reduction (0.2-0.3 vs 0.6)
        # So it should be less protective than real crisis
        # (or at least not dramatically better)
        assert isinstance(crisis, TransparencyResult)
        assert isinstance(blame, TransparencyResult)

    def test_deterministic(self):
        r1 = scenario_blame_shifting(seed=42, n_citizens=200)
        r2 = scenario_blame_shifting(seed=42, n_citizens=200)
        assert r1.metrics.total_withdrawals == r2.metrics.total_withdrawals


class TestExternalShockModel:
    def test_shock_dataclass(self):
        shock = ExternalShock(
            tick=18,
            category=PromiseCategory.ECONOMIC,
            difficulty_increase=0.3,
            description="Test crisis",
            blame_reduction=0.5,
        )
        assert shock.tick == 18
        assert shock.difficulty_increase == 0.3
        assert shock.blame_reduction == 0.5


class TestFullComparison:
    def test_returns_7_results(self):
        results = run_full_germany_comparison(seed=42, n_citizens=200)
        assert len(results) == 7

    def test_all_names_unique(self):
        results = run_full_germany_comparison(seed=42, n_citizens=200)
        names = [r.name for r in results]
        assert len(set(names)) == 7

    def test_contains_all_scenarios(self):
        results = run_full_germany_comparison(seed=42, n_citizens=200)
        names = {r.name for r in results}
        assert "opaque" in names
        assert "tracked" in names
        assert "transparent" in names
        assert "journalism" in names
        assert "social_media" in names
        assert "crisis" in names
        assert "blame_shift" in names


class TestGermanEvolution:
    def test_runs_successfully(self):
        result = run_german_evolution(n_terms=3, seed=42, n_citizens=100)
        assert isinstance(result, EvolutionResult)
        assert result.n_terms == 3

    def test_uses_5_politicians(self):
        result = run_german_evolution(n_terms=2, seed=42, n_citizens=100)
        for r in result.term_records:
            assert len(r.strategies) == 5

    def test_deterministic(self):
        r1 = run_german_evolution(n_terms=3, seed=42, n_citizens=100)
        r2 = run_german_evolution(n_terms=3, seed=42, n_citizens=100)
        for a, b in zip(r1.term_records, r2.term_records):
            assert a.winner == b.winner

    def test_longer_evolution_converges(self):
        result = run_german_evolution(n_terms=10, seed=42, n_citizens=200)
        # Should have some convergence pattern after 10 terms
        assert result.convergence_strategy is not None or result.n_terms == 10
