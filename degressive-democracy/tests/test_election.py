"""Tests for election engine."""

import pytest

from degressive_democracy.models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
)
from degressive_democracy.election import Election


class TestElectionSetup:
    def test_creates_correct_number_of_politicians(self, default_config):
        e = Election(default_config)
        assert len(e.politicians) == default_config.n_politicians

    def test_creates_correct_number_of_citizens(self, default_config):
        e = Election(default_config)
        assert len(e.citizens) == default_config.n_citizens

    def test_all_citizens_assigned_to_politician(self, default_config):
        e = Election(default_config)
        for c in e.citizens:
            assert c.politician_id != ""
            assert any(p.politician_id == c.politician_id for p in e.politicians)

    def test_votes_sum_to_total_citizens(self, default_config):
        e = Election(default_config)
        total = sum(p.initial_votes for p in e.politicians)
        assert total == default_config.n_citizens

    def test_initial_equals_current_votes(self, default_config):
        e = Election(default_config)
        for p in e.politicians:
            assert p.initial_votes == p.current_votes

    def test_promises_created_for_each_politician(self, default_config):
        e = Election(default_config)
        for p in e.politicians:
            assert len(p.promises) == default_config.promises_per_politician
            assert len(p.promise_states) == default_config.promises_per_politician

    def test_populist_gets_more_promises(self):
        config = ElectionConfig(
            n_citizens=50,
            n_politicians=2,
            term_length=48,
            seed=42,
            politician_behaviors=[
                PoliticianBehavior.POPULIST,
                PoliticianBehavior.PROMISE_KEEPER,
            ],
        )
        e = Election(config)
        populist = e.politicians[0]
        keeper = e.politicians[1]
        assert len(populist.promises) == len(keeper.promises) * 2

    def test_deterministic_with_seed(self):
        config = ElectionConfig(n_citizens=50, n_politicians=2, seed=123)
        e1 = Election(config)
        e2 = Election(config)
        ids1 = [c.behavior for c in e1.citizens]
        ids2 = [c.behavior for c in e2.citizens]
        assert ids1 == ids2


class TestElectionTick:
    def test_single_tick_runs(self, default_config):
        e = Election(default_config)
        result = e.tick(1)
        assert result.tick == 1
        assert result.avg_satisfaction > 0

    def test_power_levels_populated(self, default_config):
        e = Election(default_config)
        result = e.tick(1)
        assert len(result.power_levels) == default_config.n_politicians

    def test_no_citizen_withdraws_twice(self, default_config):
        e = Election(default_config)
        for t in range(1, default_config.term_length + 1):
            e.tick(t)
        withdrawn_ids = set()
        for tr in e.tick_results:
            for cid, _ in tr.withdrawals:
                assert cid not in withdrawn_ids, f"Citizen {cid} withdrew twice!"
                withdrawn_ids.add(cid)

    def test_total_withdrawals_leq_citizens(self, default_config):
        e = Election(default_config)
        for t in range(1, default_config.term_length + 1):
            e.tick(t)
        total = sum(len(tr.withdrawals) for tr in e.tick_results)
        assert total <= default_config.n_citizens

    def test_votes_consistent_after_run(self, default_config):
        e = Election(default_config)
        for t in range(1, default_config.term_length + 1):
            e.tick(t)
        total_remaining = sum(p.current_votes for p in e.politicians)
        total_withdrawn = sum(1 for c in e.citizens if c.has_withdrawn)
        assert total_remaining + total_withdrawn == default_config.n_citizens


class TestElectionRun:
    def test_full_run_returns_result(self, default_config):
        e = Election(default_config)
        result = e.run()
        assert result.scenario_name == "custom"
        assert len(result.tick_results) == default_config.term_length

    def test_satisfaction_trends_down_with_breakers(self):
        config = ElectionConfig(
            n_citizens=100,
            n_politicians=2,
            term_length=48,
            seed=42,
            politician_behaviors=[
                PoliticianBehavior.STRATEGIC_MIN,
                PoliticianBehavior.STRATEGIC_MIN,
            ],
        )
        e = Election(config)
        result = e.run()
        first_sat = result.tick_results[0].avg_satisfaction
        last_sat = result.tick_results[-1].avg_satisfaction
        assert last_sat <= first_sat

    def test_keeper_retains_more_votes_than_breaker(self):
        config = ElectionConfig(
            n_citizens=200,
            n_politicians=2,
            term_length=48,
            seed=42,
            politician_behaviors=[
                PoliticianBehavior.PROMISE_KEEPER,
                PoliticianBehavior.STRATEGIC_MIN,
            ],
        )
        e = Election(config)
        e.run()
        keeper = e.politicians[0]
        breaker = e.politicians[1]
        # Keeper should retain at least as many votes as the breaker
        assert keeper.current_votes >= breaker.current_votes
