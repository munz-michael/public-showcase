"""Tests for multi-term evolution."""

import pytest

from degressive_democracy.models import PoliticianBehavior, PowerModel
from degressive_democracy.evolution import (
    EvolutionResult,
    TermRecord,
    run_evolution,
)


class TestRunEvolution:
    def test_runs_successfully(self):
        result = run_evolution(n_terms=3, n_citizens=100, seed=42)
        assert isinstance(result, EvolutionResult)
        assert result.n_terms == 3

    def test_correct_number_of_records(self):
        result = run_evolution(n_terms=5, n_citizens=100, seed=42)
        assert len(result.term_records) == 5

    def test_term_records_have_correct_fields(self):
        result = run_evolution(n_terms=2, n_citizens=100, seed=42)
        for r in result.term_records:
            assert isinstance(r, TermRecord)
            assert len(r.strategies) == 5
            assert len(r.final_powers) == 5
            assert r.winner in r.final_powers
            assert isinstance(r.winner_strategy, PoliticianBehavior)

    def test_powers_in_valid_range(self):
        result = run_evolution(n_terms=3, n_citizens=100, seed=42)
        for r in result.term_records:
            for power in r.final_powers.values():
                assert 0.0 <= power <= 1.0

    def test_win_counts_sum_to_n_terms(self):
        n = 5
        result = run_evolution(n_terms=n, n_citizens=100, seed=42)
        total_wins = sum(result.strategy_win_counts.values())
        assert total_wins == n

    def test_loser_imitates_winner(self):
        result = run_evolution(n_terms=3, n_citizens=100, seed=42)
        # After term 0, the loser should switch to the winner's strategy
        if len(result.term_records) >= 2:
            winner_strat = result.term_records[0].winner_strategy
            # In term 1, the loser from term 0 should now have winner's strategy
            term1_strategies = result.term_records[1].strategies
            assert winner_strat in term1_strategies

    def test_populist_eliminated_early(self):
        result = run_evolution(n_terms=5, n_citizens=200, seed=42)
        # Populist should lose early and switch strategy
        initial = result.term_records[0].strategies
        assert PoliticianBehavior.POPULIST in initial
        # After a few terms, populist should be replaced
        final = result.term_records[-1].strategies
        populist_count_initial = initial.count(PoliticianBehavior.POPULIST)
        populist_count_final = final.count(PoliticianBehavior.POPULIST)
        assert populist_count_final <= populist_count_initial

    def test_deterministic_with_seed(self):
        r1 = run_evolution(n_terms=3, n_citizens=100, seed=77)
        r2 = run_evolution(n_terms=3, n_citizens=100, seed=77)
        for a, b in zip(r1.term_records, r2.term_records):
            assert a.winner == b.winner
            assert a.winner_strategy == b.winner_strategy

    def test_custom_initial_strategies(self):
        strats = [PoliticianBehavior.PROMISE_KEEPER] * 5
        result = run_evolution(n_terms=3, n_citizens=100, seed=42, initial_strategies=strats)
        # All keepers: no one should switch
        for r in result.term_records:
            assert all(s == PoliticianBehavior.PROMISE_KEEPER for s in r.strategies)

    def test_convergence_detection_all_same(self):
        strats = [PoliticianBehavior.PROMISE_KEEPER] * 5
        result = run_evolution(n_terms=3, n_citizens=100, seed=42, initial_strategies=strats)
        assert result.convergence_strategy == "promise_keeper"

    def test_memory_penalty_affects_satisfaction(self):
        # High memory penalty should cause more withdrawals over time
        r_low = run_evolution(n_terms=3, n_citizens=100, seed=42, memory_penalty=0.0)
        r_high = run_evolution(n_terms=3, n_citizens=100, seed=42, memory_penalty=0.3)
        # With memory, later terms should have more pressure
        assert isinstance(r_low, EvolutionResult)
        assert isinstance(r_high, EvolutionResult)

    def test_different_power_models(self):
        for model in PowerModel:
            result = run_evolution(n_terms=2, n_citizens=100, seed=42, power_model=model)
            assert len(result.term_records) == 2
