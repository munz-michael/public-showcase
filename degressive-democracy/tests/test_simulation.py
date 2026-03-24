"""Tests for predefined simulation scenarios."""

import pytest

from degressive_democracy.simulation import (
    ALL_SCENARIOS,
    scenario_baseline,
    scenario_single_breaker,
    scenario_all_break,
    scenario_coordinated_attack,
    scenario_populist_wave,
    scenario_coalition_dynamics,
    scenario_adaptive_response,
    scenario_power_model_comparison,
    scenario_citizen_mix,
)


class TestBaseline:
    def test_runs_successfully(self):
        result, metrics = scenario_baseline()
        assert result.scenario_name == "baseline"
        assert len(result.tick_results) == 48

    def test_high_satisfaction(self):
        _, metrics = scenario_baseline()
        # Promise keepers should maintain decent satisfaction
        assert metrics.avg_final_satisfaction > 0.3

    def test_fewer_withdrawals_than_breakers(self):
        _, baseline_metrics = scenario_baseline()
        _, breaker_metrics = scenario_all_break()
        # Promise keepers should lose fewer votes than breakers
        assert baseline_metrics.total_withdrawals <= breaker_metrics.total_withdrawals


class TestSingleBreaker:
    def test_runs_successfully(self):
        result, metrics = scenario_single_breaker()
        assert result.scenario_name == "single_breaker"

    def test_breaker_loses_more_votes(self):
        result, metrics = scenario_single_breaker()
        # pol_0 is strategic_min, should lose more
        power_0 = metrics.final_power_levels.get("pol_0", 1.0)
        power_1 = metrics.final_power_levels.get("pol_1", 1.0)
        assert power_0 <= power_1


class TestAllBreak:
    def test_runs_successfully(self):
        result, metrics = scenario_all_break()
        assert result.scenario_name == "all_break"

    def test_withdrawals_occur(self):
        _, metrics = scenario_all_break()
        assert metrics.total_withdrawals > 0


class TestCoordinatedAttack:
    def test_runs_successfully(self):
        result, metrics = scenario_coordinated_attack()
        assert result.scenario_name == "coordinated_attack"

    def test_spike_withdrawal_around_attack_tick(self):
        result, _ = scenario_coordinated_attack()
        # Satisfaction tanked at hook tick 23, withdrawals happen at tick 23
        tick_23 = result.tick_results[22]  # 0-indexed
        assert len(tick_23.withdrawals) > 10  # significant spike from forced satisfaction drop

    def test_more_withdrawals_than_baseline(self):
        _, attack_metrics = scenario_coordinated_attack()
        _, baseline_metrics = scenario_baseline()
        assert attack_metrics.total_withdrawals >= baseline_metrics.total_withdrawals


class TestPopulistWave:
    def test_runs_successfully(self):
        result, metrics = scenario_populist_wave()
        assert result.scenario_name == "populist_wave"

    def test_populist_loses_power(self):
        _, metrics = scenario_populist_wave()
        populist_power = metrics.final_power_levels.get("pol_0", 1.0)
        # Populist should lose power due to thin effort spread
        assert populist_power < 1.0


class TestCoalitionDynamics:
    def test_runs_successfully(self):
        result, metrics = scenario_coalition_dynamics()
        assert result.scenario_name == "coalition_dynamics"

    def test_uses_threshold_model(self):
        result, _ = scenario_coalition_dynamics()
        assert result.config.power_model == "threshold" or result.config.power_model.value == "threshold"


class TestAdaptiveResponse:
    def test_runs_successfully(self):
        result, metrics = scenario_adaptive_response()
        assert result.scenario_name == "adaptive_response"

    def test_all_politicians_adaptive(self):
        result, _ = scenario_adaptive_response()
        # Should complete without errors with all adaptive
        assert len(result.tick_results) == 48


class TestPowerModelComparison:
    def test_runs_all_models(self):
        results = scenario_power_model_comparison()
        assert len(results) == 4
        for model_name in ["linear", "threshold", "convex", "logarithmic"]:
            assert model_name in results

    def test_all_models_produce_results(self):
        results = scenario_power_model_comparison()
        for model_name, (result, metrics) in results.items():
            assert len(result.tick_results) == 48
            assert metrics.total_withdrawals >= 0


class TestCitizenMix:
    def test_runs_successfully(self):
        result, metrics = scenario_citizen_mix()
        assert result.scenario_name == "citizen_mix"
        assert len(result.tick_results) == 48

    def test_larger_population(self):
        result, _ = scenario_citizen_mix()
        assert result.config.n_citizens == 500

    def test_mixed_strategies_produce_varied_power(self):
        _, metrics = scenario_citizen_mix()
        powers = list(metrics.final_power_levels.values())
        assert max(powers) - min(powers) > 0.01  # some variation expected


class TestScenarioRegistry:
    def test_all_scenarios_registered(self):
        assert len(ALL_SCENARIOS) == 10

    def test_all_scenarios_callable(self):
        for name, fn in ALL_SCENARIOS.items():
            assert callable(fn), f"Scenario {name} is not callable"


class TestDeterminism:
    def test_same_seed_same_result(self):
        r1, m1 = scenario_baseline(seed=99)
        r2, m2 = scenario_baseline(seed=99)
        assert m1.total_withdrawals == m2.total_withdrawals
        assert m1.avg_final_satisfaction == m2.avg_final_satisfaction

    def test_different_seed_different_result(self):
        _, m1 = scenario_citizen_mix(seed=1)
        _, m2 = scenario_citizen_mix(seed=999)
        # With different seeds, withdrawal curves should differ even if totals match
        assert (
            m1.total_withdrawals != m2.total_withdrawals
            or m1.peak_withdrawal_tick != m2.peak_withdrawal_tick
            or m1.promise_fulfillment_rate != m2.promise_fulfillment_rate
        )
