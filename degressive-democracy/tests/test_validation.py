"""Tests for cross-validation: game theory vs. simulation."""

import pytest

from degressive_democracy.models import PowerModel
from degressive_democracy.validation import (
    ValidationResult,
    StrategyEmpirical,
    validate_nash,
)


class TestValidateNash:
    def test_runs_successfully(self):
        result = validate_nash(n_citizens=100, n_runs=2, seed=42)
        assert isinstance(result, ValidationResult)

    def test_returns_all_strategies(self):
        result = validate_nash(n_citizens=100, n_runs=2, seed=42)
        assert len(result.strategy_results) == 5
        assert "promise_keeper" in result.strategy_results
        assert "strategic_minimum" in result.strategy_results
        assert "populist" in result.strategy_results
        assert "frontloader" in result.strategy_results
        assert "adaptive" in result.strategy_results

    def test_nash_prediction_is_bool(self):
        result = validate_nash(n_citizens=100, n_runs=2, seed=42)
        assert isinstance(result.nash_predicts_keeper, bool)
        assert isinstance(result.simulation_confirms, bool)
        assert isinstance(result.match, bool)

    def test_match_is_consistent(self):
        result = validate_nash(n_citizens=100, n_runs=2, seed=42)
        assert result.match == (result.nash_predicts_keeper == result.simulation_confirms)

    def test_keeper_has_high_power(self):
        result = validate_nash(n_citizens=200, n_runs=3, seed=42)
        keeper = result.strategy_results["promise_keeper"]
        assert keeper.final_power >= 0.8

    def test_populist_has_low_power(self):
        result = validate_nash(n_citizens=200, n_runs=3, seed=42)
        populist = result.strategy_results["populist"]
        assert populist.final_power < 0.5

    def test_keeper_fulfills_more_than_populist(self):
        result = validate_nash(n_citizens=200, n_runs=3, seed=42)
        keeper = result.strategy_results["promise_keeper"]
        populist = result.strategy_results["populist"]
        assert keeper.promise_fulfillment > populist.promise_fulfillment

    def test_discrepancies_is_list(self):
        result = validate_nash(n_citizens=100, n_runs=2, seed=42)
        assert isinstance(result.discrepancies, list)

    def test_deterministic_with_seed(self):
        r1 = validate_nash(n_citizens=100, n_runs=2, seed=99)
        r2 = validate_nash(n_citizens=100, n_runs=2, seed=99)
        assert r1.nash_predicts_keeper == r2.nash_predicts_keeper
        assert r1.simulation_confirms == r2.simulation_confirms

    def test_different_power_models(self):
        for model in [PowerModel.LINEAR, PowerModel.THRESHOLD]:
            result = validate_nash(n_citizens=100, n_runs=1, seed=42, power_model=model)
            assert isinstance(result, ValidationResult)

    def test_strategy_empirical_fields(self):
        result = validate_nash(n_citizens=100, n_runs=2, seed=42)
        for name, s in result.strategy_results.items():
            assert isinstance(s, StrategyEmpirical)
            assert 0.0 <= s.final_power <= 1.0
            assert 0.0 <= s.withdrawal_rate <= 1.0
            assert 0.0 <= s.promise_fulfillment <= 1.0
            assert 0.0 <= s.avg_citizen_satisfaction <= 1.0
