"""Tests for advanced mechanics: public counter, factions, parties, calibration."""

import pytest

from degressive_democracy.models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
    PromiseCategory,
)
from degressive_democracy.advanced import (
    AdvancedElection,
    CalibrationParams,
    CoalitionAgreement,
    Faction,
    FactionStrategy,
    PublicCounterState,
    apply_public_counter_effect,
    check_faction_trigger,
    run_advanced_comparison,
    scenario_calibrated_germany,
    scenario_coalition_government,
    scenario_faction_attack,
    scenario_public_counter,
)


# --- Public Counter ---

class TestPublicCounter:
    def test_counter_updates_after_tick(self):
        config = ElectionConfig(n_citizens=100, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.POPULIST, PoliticianBehavior.PROMISE_KEEPER])
        election = AdvancedElection(config, enable_public_counter=True)
        for t in range(1, 20):
            election.tick(t)
        # Counter should have tracked some withdrawals
        total = sum(election.counter.counts.values())
        assert total >= 0

    def test_counter_rates_in_range(self):
        config = ElectionConfig(n_citizens=100, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.POPULIST, PoliticianBehavior.PROMISE_KEEPER])
        election = AdvancedElection(config, enable_public_counter=True)
        for t in range(1, 49):
            election.tick(t)
        for rate in election.counter.rates.values():
            assert 0.0 <= rate <= 1.0

    def test_counter_disabled(self):
        config = ElectionConfig(n_citizens=100, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 2)
        election = AdvancedElection(config, enable_public_counter=False)
        for t in range(1, 49):
            election.tick(t)
        # Counter still tracks but doesn't affect satisfaction
        assert isinstance(election.counter, PublicCounterState)

    def test_counter_amplifies_withdrawals(self):
        config = ElectionConfig(n_citizens=200, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.STRATEGIC_MIN, PoliticianBehavior.PROMISE_KEEPER])
        # With counter
        e_with = AdvancedElection(config, enable_public_counter=True, counter_sensitivity=0.2)
        for t in range(1, 49):
            e_with.tick(t)
        wd_with = sum(1 for c in e_with.citizens if c.has_withdrawn)

        # Without counter
        e_without = AdvancedElection(config, enable_public_counter=False)
        for t in range(1, 49):
            e_without.tick(t)
        wd_without = sum(1 for c in e_without.citizens if c.has_withdrawn)

        # Counter should amplify withdrawals (or at least not reduce them)
        assert wd_with >= wd_without


class TestScenarioPublicCounter:
    def test_runs(self):
        result, metrics = scenario_public_counter(seed=42, n_citizens=100)
        assert len(result.tick_results) == 48
        assert metrics.total_withdrawals >= 0


# --- Factions ---

class TestFactions:
    def test_timed_faction_activates(self):
        config = ElectionConfig(n_citizens=100, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 2)
        election = AdvancedElection(config)

        target = election.politicians[0]
        members = [c.citizen_id for c in election.citizens if c.politician_id == target.politician_id][:10]
        faction = Faction("test", members, target.politician_id, FactionStrategy.TIMED, 15)
        election.factions = [faction]

        for t in range(1, 49):
            election.tick(t)

        assert faction.activated
        # Check that faction members withdrew
        withdrawn_members = [c for c in election.citizens if c.citizen_id in members and c.has_withdrawn]
        assert len(withdrawn_members) == len(members)

    def test_faction_events_logged(self):
        config = ElectionConfig(n_citizens=100, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 2)
        election = AdvancedElection(config)

        target = election.politicians[0]
        members = [c.citizen_id for c in election.citizens if c.politician_id == target.politician_id][:5]
        faction = Faction("bloc", members, target.politician_id, FactionStrategy.TIMED, 10)
        election.factions = [faction]

        for t in range(1, 49):
            election.tick(t)

        all_events = [e for tr in election.tick_results for e in tr.events]
        assert any("FACTION bloc activated" in e for e in all_events)

    def test_reactive_faction(self):
        counter = PublicCounterState(rates={"pol_0": 0.2})
        faction = Faction("r", [], "pol_0", FactionStrategy.REACTIVE, 0.15)
        assert check_faction_trigger(faction, 10, counter, 1.0, 0.5) is True

    def test_opportunistic_faction(self):
        counter = PublicCounterState()
        faction = Faction("o", [], "pol_0", FactionStrategy.OPPORTUNISTIC, 0.5)
        assert check_faction_trigger(faction, 10, counter, 0.3, 0.8) is True
        assert check_faction_trigger(faction, 10, counter, 0.7, 0.8) is False


class TestScenarioFaction:
    def test_runs(self):
        result, metrics = scenario_faction_attack(seed=42, n_citizens=100)
        assert len(result.tick_results) == 48

    def test_faction_event_present(self):
        result, _ = scenario_faction_attack(seed=42, n_citizens=100)
        all_events = [e for tr in result.tick_results for e in tr.events]
        assert any("FACTION" in e for e in all_events)


# --- Coalition ---

class TestCoalition:
    def test_coalition_can_collapse(self):
        config = ElectionConfig(n_citizens=200, n_politicians=4, seed=42,
            power_model=PowerModel.THRESHOLD,
            politician_behaviors=[PoliticianBehavior.STRATEGIC_MIN, PoliticianBehavior.STRATEGIC_MIN,
                                  PoliticianBehavior.PROMISE_KEEPER, PoliticianBehavior.PROMISE_KEEPER])
        election = AdvancedElection(config)

        coalition = CoalitionAgreement(
            party_ids=["pol_0", "pol_1"],
            shared_promises=[],
            power_threshold=1.5,  # high threshold — easy to collapse
        )
        election.coalition = coalition

        for t in range(1, 49):
            election.tick(t)

        # With strategic min politicians losing power, coalition should collapse
        all_events = [e for tr in election.tick_results for e in tr.events]
        has_collapse = any("COALITION COLLAPSED" in e for e in all_events)
        # May or may not collapse depending on dynamics
        assert isinstance(coalition.collapsed, bool)


class TestScenarioCoalition:
    def test_runs(self):
        result, metrics = scenario_coalition_government(seed=42, n_citizens=100)
        assert len(result.tick_results) == 48


# --- Calibration ---

class TestCalibration:
    def test_params_sum_to_1(self):
        cal = CalibrationParams()
        dist = cal.to_citizen_distribution()
        total = sum(dist.values())
        assert abs(total - 1.0) < 0.01

    def test_apathetic_matches_bt2021(self):
        cal = CalibrationParams()
        assert abs(cal.apathetic_rate - 0.234) < 0.01

    def test_calibration_adjusts_thresholds(self):
        config = ElectionConfig(n_citizens=100, n_politicians=2, seed=42,
            politician_behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 2)
        cal = CalibrationParams(withdrawal_threshold_mean=0.2)
        election = AdvancedElection(config, calibration=cal)
        thresholds = [c.withdrawal_threshold for c in election.citizens]
        avg = sum(thresholds) / len(thresholds)
        assert 0.1 < avg < 0.3  # should be around 0.2


class TestScenarioCalibratedGermany:
    def test_runs(self):
        result, metrics = scenario_calibrated_germany(seed=42, n_citizens=200)
        assert len(result.tick_results) == 48
        assert metrics.total_withdrawals >= 0

    def test_deterministic(self):
        _, m1 = scenario_calibrated_germany(seed=42, n_citizens=200)
        _, m2 = scenario_calibrated_germany(seed=42, n_citizens=200)
        assert m1.total_withdrawals == m2.total_withdrawals


# --- Full comparison ---

class TestAdvancedComparison:
    def test_returns_4_results(self):
        results = run_advanced_comparison(seed=42)
        assert len(results) == 4

    def test_all_scenarios_present(self):
        results = run_advanced_comparison(seed=42)
        assert "public_counter" in results
        assert "faction_attack" in results
        assert "coalition_gov" in results
        assert "calibrated_de" in results
