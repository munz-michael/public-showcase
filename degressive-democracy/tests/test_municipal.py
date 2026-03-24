"""Tests for municipal level comparison."""

import pytest

from degressive_democracy.municipal import (
    ALL_LEVELS,
    KOMMUNE,
    KREISSTADT,
    GROSSSTADT,
    BUNDESTAG,
    LevelResult,
    run_level,
    run_municipal_comparison,
)


class TestGovernmentLevels:
    def test_four_levels_defined(self):
        assert len(ALL_LEVELS) == 4

    def test_visibility_decreases_with_size(self):
        assert KOMMUNE.avg_visibility > KREISSTADT.avg_visibility
        assert KREISSTADT.avg_visibility > GROSSSTADT.avg_visibility

    def test_kommune_highest_concreteness(self):
        assert KOMMUNE.promise_concreteness > BUNDESTAG.promise_concreteness

    def test_faction_risk_increases_with_size(self):
        assert KOMMUNE.faction_risk <= BUNDESTAG.faction_risk


class TestRunLevel:
    def test_kommune_runs(self):
        result = run_level(KOMMUNE, seed=42)
        assert isinstance(result, LevelResult)
        assert len(result.result.tick_results) == 48

    def test_bundestag_runs(self):
        result = run_level(BUNDESTAG, seed=42)
        assert isinstance(result, LevelResult)

    def test_kommune_high_satisfaction(self):
        result = run_level(KOMMUNE, seed=42)
        assert result.metrics.avg_final_satisfaction >= 0.8

    def test_kommune_few_withdrawals(self):
        result = run_level(KOMMUNE, seed=42)
        # High transparency should mean few or no withdrawals
        assert result.metrics.total_withdrawals <= 10

    def test_power_in_range(self):
        for level in ALL_LEVELS:
            result = run_level(level, seed=42)
            assert 0.0 <= result.keeper_power <= 1.0
            assert 0.0 <= result.stratmin_power <= 1.0

    def test_deterministic(self):
        r1 = run_level(KOMMUNE, seed=42)
        r2 = run_level(KOMMUNE, seed=42)
        assert r1.metrics.total_withdrawals == r2.metrics.total_withdrawals

    def test_with_faction(self):
        result = run_level(KREISSTADT, seed=42, with_faction=True)
        assert isinstance(result, LevelResult)

    def test_without_faction(self):
        result = run_level(KREISSTADT, seed=42, with_faction=False)
        assert result.faction_events == 0


class TestMunicipalComparison:
    def test_returns_4_results(self):
        results = run_municipal_comparison(seed=42)
        assert len(results) == 4

    def test_all_levels_present(self):
        results = run_municipal_comparison(seed=42)
        names = [r.level.name for r in results]
        assert "Kommune (5.000 EW)" in names
        assert "Bundestag (60 Mio)" in names

    def test_kommune_best_satisfaction(self):
        results = run_municipal_comparison(seed=42)
        kommune = results[0]
        for r in results[1:]:
            assert kommune.metrics.avg_final_satisfaction >= r.metrics.avg_final_satisfaction
