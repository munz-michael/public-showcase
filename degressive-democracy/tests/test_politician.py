"""Tests for politician agent behavior."""

import pytest

from degressive_democracy.models import (
    PoliticianBehavior,
    PoliticianState,
    PowerModel,
    Promise,
    PromiseCategory,
    PromiseState,
    PromiseStatus,
)
from degressive_democracy.politician import (
    allocate_effort,
    update_power,
)


class TestAllocateEffort:
    def test_promise_keeper_progresses_all(self, basic_politician):
        allocate_effort(basic_politician, tick=1, term_length=48)
        for ps in basic_politician.promise_states.values():
            assert ps.progress > 0.0
            assert ps.effort_invested > 0.0

    def test_promise_keeper_equal_distribution(self, basic_politician):
        allocate_effort(basic_politician, tick=1, term_length=48)
        efforts = [ps.effort_invested for ps in basic_politician.promise_states.values()]
        # All should get roughly equal effort
        assert max(efforts) - min(efforts) < 0.01

    def test_strategic_min_ignores_low_visibility(self, basic_politician):
        basic_politician.behavior = PoliticianBehavior.STRATEGIC_MIN
        allocate_effort(basic_politician, tick=1, term_length=48)
        # p4 has visibility 0.3 (below 0.5 threshold)
        assert basic_politician.promise_states["p4"].effort_invested == 0.0

    def test_strategic_min_invests_in_visible(self, basic_politician):
        basic_politician.behavior = PoliticianBehavior.STRATEGIC_MIN
        allocate_effort(basic_politician, tick=1, term_length=48)
        # p1 (0.8), p2 (0.9), p5 (0.6) should get effort
        assert basic_politician.promise_states["p1"].effort_invested > 0.0
        assert basic_politician.promise_states["p2"].effort_invested > 0.0
        assert basic_politician.promise_states["p5"].effort_invested > 0.0

    def test_frontloader_easiest_first(self, basic_politician):
        basic_politician.behavior = PoliticianBehavior.FRONTLOADER
        allocate_effort(basic_politician, tick=1, term_length=48)
        # p5 (difficulty 0.3) should get more progress than p2 (difficulty 0.7)
        assert basic_politician.promise_states["p5"].progress >= basic_politician.promise_states["p2"].progress

    def test_populist_thin_spread(self, basic_politician):
        basic_politician.behavior = PoliticianBehavior.POPULIST
        allocate_effort(basic_politician, tick=1, term_length=48)
        # Each promise should get some but little effort
        for ps in basic_politician.promise_states.values():
            assert ps.effort_invested > 0.0
            assert ps.effort_invested < basic_politician.effort_budget_per_tick / 2

    def test_adaptive_relaxed_equals_keeper(self, basic_politician):
        basic_politician.behavior = PoliticianBehavior.ADAPTIVE
        allocate_effort(basic_politician, tick=1, term_length=48, withdrawal_rate=0.0)
        efforts = [ps.effort_invested for ps in basic_politician.promise_states.values()]
        # Should behave like equal distribution when no pressure
        assert max(efforts) - min(efforts) < 0.01

    def test_adaptive_under_pressure_focuses(self, basic_politician):
        basic_politician.behavior = PoliticianBehavior.ADAPTIVE
        allocate_effort(basic_politician, tick=1, term_length=48, withdrawal_rate=0.2)
        # Under pressure: should ignore low-visibility (like strategic_min)
        assert basic_politician.promise_states["p4"].effort_invested == 0.0

    def test_power_reduces_effective_effort(self, basic_politician):
        basic_politician.power = 0.5
        allocate_effort(basic_politician, tick=1, term_length=48)
        effort_half = sum(ps.effort_invested for ps in basic_politician.promise_states.values())

        # Reset
        for ps in basic_politician.promise_states.values():
            ps.effort_invested = 0.0
            ps.progress = 0.0
        basic_politician.power = 1.0
        allocate_effort(basic_politician, tick=1, term_length=48)
        effort_full = sum(ps.effort_invested for ps in basic_politician.promise_states.values())

        assert effort_half < effort_full

    def test_fulfilled_promise_excluded(self, basic_politician):
        basic_politician.promise_states["p1"].status = PromiseStatus.FULFILLED
        basic_politician.promise_states["p1"].progress = 1.0
        old_effort = basic_politician.promise_states["p1"].effort_invested
        allocate_effort(basic_politician, tick=1, term_length=48)
        assert basic_politician.promise_states["p1"].effort_invested == old_effort

    def test_no_active_promises_noop(self, basic_politician):
        for ps in basic_politician.promise_states.values():
            ps.status = PromiseStatus.FULFILLED
        allocate_effort(basic_politician, tick=1, term_length=48)  # should not raise

    def test_progress_capped_at_1(self, basic_politician):
        for ps in basic_politician.promise_states.values():
            ps.progress = 0.99
        for _ in range(50):
            allocate_effort(basic_politician, tick=1, term_length=48)
        for ps in basic_politician.promise_states.values():
            assert ps.progress <= 1.0


class TestUpdatePower:
    def test_full_votes_full_power(self, basic_politician):
        power = update_power(basic_politician, PowerModel.LINEAR)
        assert power == 1.0

    def test_half_votes_half_power(self, basic_politician):
        basic_politician.current_votes = 100
        power = update_power(basic_politician, PowerModel.LINEAR)
        assert power == 0.5

    def test_zero_votes_zero_power(self, basic_politician):
        basic_politician.current_votes = 0
        power = update_power(basic_politician, PowerModel.LINEAR)
        assert power == 0.0

    def test_power_written_to_state(self, basic_politician):
        basic_politician.current_votes = 100
        update_power(basic_politician, PowerModel.LINEAR)
        assert basic_politician.power == 0.5

    def test_threshold_model(self, basic_politician):
        basic_politician.current_votes = 60  # 60/200 = 0.3 -> bracket 0.25-0.5 -> 0.2
        power = update_power(basic_politician, PowerModel.THRESHOLD)
        assert power == 0.2
