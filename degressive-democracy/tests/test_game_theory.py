"""Tests for game theory analysis."""

import pytest

from degressive_democracy.models import PowerModel
from degressive_democracy.game_theory import (
    CoordinationBound,
    DegressivePayoffParams,
    NashResult,
    SweepResult,
    check_nash_equilibrium,
    compute_breaker_payoff,
    compute_keeper_payoff,
    compute_populist_payoff,
    compute_strategic_min_payoff,
    coordination_attack_bounds,
    parameter_sweep,
)


class TestPayoffComputation:
    def test_keeper_payoff_positive(self):
        p = compute_keeper_payoff(DegressivePayoffParams())
        assert p.total_utility > 0
        assert p.strategy == "keeper"

    def test_breaker_1_lower_than_keeper(self):
        params = DegressivePayoffParams()
        keeper = compute_keeper_payoff(params)
        breaker = compute_breaker_payoff(params, n_broken=1)
        assert keeper.total_utility > breaker.total_utility

    def test_breaker_all_much_lower(self):
        params = DegressivePayoffParams()
        keeper = compute_keeper_payoff(params)
        breaker = compute_breaker_payoff(params, n_broken=5)
        assert keeper.total_utility > breaker.total_utility

    def test_populist_lower_than_keeper(self):
        params = DegressivePayoffParams()
        keeper = compute_keeper_payoff(params)
        populist = compute_populist_payoff(params)
        assert keeper.total_utility > populist.total_utility

    def test_strategic_min_between_keeper_and_breaker(self):
        params = DegressivePayoffParams()
        keeper = compute_keeper_payoff(params)
        strat = compute_strategic_min_payoff(params)
        breaker_all = compute_breaker_payoff(params, n_broken=5)
        # Strategic min should be between full keeper and full breaker
        assert breaker_all.total_utility <= strat.total_utility <= keeper.total_utility

    def test_more_broken_less_power(self):
        params = DegressivePayoffParams()
        b1 = compute_breaker_payoff(params, n_broken=1)
        b3 = compute_breaker_payoff(params, n_broken=3)
        assert b1.final_power >= b3.final_power

    def test_keeper_retains_most_votes(self):
        params = DegressivePayoffParams()
        keeper = compute_keeper_payoff(params)
        breaker = compute_breaker_payoff(params, n_broken=3)
        assert keeper.final_votes > breaker.final_votes

    def test_payoff_with_different_power_models(self):
        for model in PowerModel:
            params = DegressivePayoffParams(power_model=model)
            keeper = compute_keeper_payoff(params)
            assert keeper.total_utility > 0
            assert 0.0 <= keeper.final_power <= 1.0


class TestNashEquilibrium:
    def test_default_params_is_nash(self):
        result = check_nash_equilibrium()
        assert result.is_nash is True
        assert result.dominant_strategy == "keeper"

    def test_all_deviation_gains_negative(self):
        result = check_nash_equilibrium()
        for strategy, gain in result.deviation_gains.items():
            assert gain <= 0, f"Strategy {strategy} has positive deviation gain"

    def test_high_broken_benefit_breaks_nash(self):
        params = DegressivePayoffParams(benefit_broken=5.0)
        result = check_nash_equilibrium(params)
        assert result.is_nash is False

    def test_high_withdrawal_rate_strengthens_nash(self):
        params = DegressivePayoffParams(withdrawal_rate_per_broken=0.5)
        result = check_nash_equilibrium(params)
        assert result.is_nash is True
        # All deviations should be strongly negative
        for gain in result.deviation_gains.values():
            assert gain < -1.0

    def test_zero_withdrawal_rate_breaks_nash(self):
        params = DegressivePayoffParams(
            withdrawal_rate_per_broken=0.0,
            benefit_broken=0.5,
        )
        result = check_nash_equilibrium(params)
        # Without withdrawals, breaking is free -> Nash breaks
        assert result.is_nash is False

    def test_result_has_condition_string(self):
        result = check_nash_equilibrium()
        assert len(result.condition) > 0
        assert "Nash" in result.condition


class TestParameterSweep:
    def test_sweep_benefit_broken(self):
        result = parameter_sweep(
            "benefit_broken",
            [0.0, 0.1, 0.5, 1.0, 2.0, 5.0],
        )
        assert len(result.nash_results) == 6
        # Low values should be Nash, high values should break
        assert result.nash_results[0] is True  # benefit_broken=0
        assert result.nash_results[-1] is False  # benefit_broken=5

    def test_sweep_finds_critical_value(self):
        result = parameter_sweep(
            "benefit_broken",
            [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
        )
        assert result.critical_value is not None

    def test_sweep_withdrawal_rate(self):
        result = parameter_sweep(
            "withdrawal_rate_per_broken",
            [0.0, 0.05, 0.10, 0.15, 0.20, 0.30],
        )
        assert len(result.nash_results) == 6
        # High withdrawal rate should maintain Nash
        assert result.nash_results[-1] is True

    def test_sweep_across_power_models(self):
        for model in PowerModel:
            params = DegressivePayoffParams(power_model=model)
            result = parameter_sweep(
                "benefit_broken",
                [0.0, 1.0, 3.0, 5.0],
                base_params=params,
            )
            assert len(result.nash_results) == 4


class TestCoordinationBounds:
    def test_threshold_model_returns_3_bounds(self):
        bounds = coordination_attack_bounds(200, PowerModel.THRESHOLD)
        assert len(bounds) == 3

    def test_linear_model_returns_3_bounds(self):
        bounds = coordination_attack_bounds(200, PowerModel.LINEAR)
        assert len(bounds) == 3

    def test_fractions_increase(self):
        bounds = coordination_attack_bounds(200, PowerModel.THRESHOLD)
        fractions = [b.fraction_needed for b in bounds]
        assert fractions == sorted(fractions)

    def test_votes_needed_positive(self):
        bounds = coordination_attack_bounds(200, PowerModel.THRESHOLD)
        for b in bounds:
            assert b.votes_needed > 0
            assert 0 < b.fraction_needed < 1

    def test_threshold_specific_values(self):
        bounds = coordination_attack_bounds(100, PowerModel.THRESHOLD)
        # To drop below 75%: need to remove 25 votes (25%)
        assert bounds[0].votes_needed == 25
        assert bounds[0].fraction_needed == 0.25
