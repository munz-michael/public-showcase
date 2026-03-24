"""Tests for citizen agent behavior."""

import pytest

from degressive_democracy.models import (
    CitizenBehavior,
    CitizenState,
    PoliticianBehavior,
    PoliticianState,
    Promise,
    PromiseCategory,
    PromiseState,
    PromiseStatus,
)
from degressive_democracy.citizen import (
    decide_withdrawal,
    execute_withdrawal,
    update_satisfaction,
)


@pytest.fixture
def politician_with_progress(basic_promises, basic_politician):
    """Politician with some promise progress."""
    pol = basic_politician
    for ps in pol.promise_states.values():
        ps.progress = 0.5
        ps.status = PromiseStatus.PROGRESSING
    return pol


class TestUpdateSatisfaction:
    def test_satisfaction_stays_high_with_progress(self, rational_citizen, politician_with_progress):
        sat = update_satisfaction(rational_citizen, politician_with_progress, tick=24)
        assert sat >= 0.8  # on track at half term

    def test_satisfaction_drops_with_no_progress(self, rational_citizen, basic_politician):
        # No progress at tick 24 = behind schedule
        sat = update_satisfaction(rational_citizen, basic_politician, tick=24)
        assert sat < 1.0

    def test_satisfaction_clamped_0_1(self, rational_citizen, basic_politician):
        rational_citizen.satisfaction = 0.01
        # All broken
        for ps in basic_politician.promise_states.values():
            ps.status = PromiseStatus.BROKEN
        sat = update_satisfaction(rational_citizen, basic_politician, tick=24)
        assert 0.0 <= sat <= 1.0

    def test_fulfilled_promise_boosts_satisfaction(self, rational_citizen, basic_politician):
        for ps in basic_politician.promise_states.values():
            ps.status = PromiseStatus.FULFILLED
            ps.progress = 1.0
        initial = rational_citizen.satisfaction
        update_satisfaction(rational_citizen, basic_politician, tick=24)
        assert rational_citizen.satisfaction >= initial

    def test_broken_promise_lowers_satisfaction(self, rational_citizen, basic_politician):
        for ps in basic_politician.promise_states.values():
            ps.status = PromiseStatus.BROKEN
        initial = rational_citizen.satisfaction
        update_satisfaction(rational_citizen, basic_politician, tick=24)
        assert rational_citizen.satisfaction < initial

    def test_no_promises_keeps_satisfaction(self, rational_citizen):
        empty_pol = PoliticianState("pol2", PoliticianBehavior.PROMISE_KEEPER)
        initial = rational_citizen.satisfaction
        update_satisfaction(rational_citizen, empty_pol, tick=10)
        assert rational_citizen.satisfaction == initial

    def test_priority_categories_weight_more(self, rational_citizen, basic_politician):
        rational_citizen.priority_categories = [PromiseCategory.ECONOMIC]
        # Break only the economic promise
        basic_politician.promise_states["p1"].status = PromiseStatus.BROKEN
        for pid in ["p2", "p3", "p4", "p5"]:
            basic_politician.promise_states[pid].progress = 0.5
            basic_politician.promise_states[pid].status = PromiseStatus.PROGRESSING
        update_satisfaction(rational_citizen, basic_politician, tick=24)
        sat_with_priority = rational_citizen.satisfaction

        # Reset and try without priority
        rational_citizen.satisfaction = 1.0
        rational_citizen.priority_categories = []
        update_satisfaction(rational_citizen, basic_politician, tick=24)
        sat_without = rational_citizen.satisfaction

        # Priority on broken promise should hurt more
        assert sat_with_priority < sat_without


class TestDecideWithdrawal:
    def test_rational_withdraws_below_threshold(self):
        c = CitizenState("c1", CitizenBehavior.RATIONAL, "pol1", satisfaction=0.3, withdrawal_threshold=0.4)
        assert decide_withdrawal(c, tick=10, term_length=48) is True

    def test_rational_stays_above_threshold(self):
        c = CitizenState("c1", CitizenBehavior.RATIONAL, "pol1", satisfaction=0.5, withdrawal_threshold=0.4)
        assert decide_withdrawal(c, tick=10, term_length=48) is False

    def test_already_withdrawn_cannot_withdraw_again(self):
        c = CitizenState("c1", CitizenBehavior.RATIONAL, "pol1", satisfaction=0.1, has_withdrawn=True)
        assert decide_withdrawal(c, tick=10, term_length=48) is False

    def test_apathetic_never_withdraws(self):
        c = CitizenState("c1", CitizenBehavior.APATHETIC, "pol1", satisfaction=0.0)
        assert decide_withdrawal(c, tick=10, term_length=48) is False

    def test_loyal_high_tolerance(self):
        c = CitizenState("c1", CitizenBehavior.LOYAL, "pol1", satisfaction=0.25, withdrawal_threshold=0.4)
        assert decide_withdrawal(c, tick=10, term_length=48) is False  # threshold capped at 0.2

    def test_loyal_eventually_withdraws(self):
        c = CitizenState("c1", CitizenBehavior.LOYAL, "pol1", satisfaction=0.1, withdrawal_threshold=0.4)
        assert decide_withdrawal(c, tick=10, term_length=48) is True

    def test_volatile_quick_trigger(self):
        c = CitizenState("c1", CitizenBehavior.VOLATILE, "pol1", satisfaction=0.55, withdrawal_threshold=0.4)
        assert decide_withdrawal(c, tick=10, term_length=48) is True  # threshold raised to 0.6

    def test_peer_influenced_without_peer_pressure(self):
        c = CitizenState("c1", CitizenBehavior.PEER_INFLUENCED, "pol1", satisfaction=0.5, withdrawal_threshold=0.4)
        assert decide_withdrawal(c, tick=10, term_length=48, peer_withdrawal_rate=0.1) is False

    def test_peer_influenced_with_peer_pressure(self):
        c = CitizenState("c1", CitizenBehavior.PEER_INFLUENCED, "pol1", satisfaction=0.5, withdrawal_threshold=0.4)
        # peer rate > 0.3 raises threshold by 0.15 -> effective 0.55
        assert decide_withdrawal(c, tick=10, term_length=48, peer_withdrawal_rate=0.5) is True

    def test_strategic_waits_for_late_term(self):
        c = CitizenState("c1", CitizenBehavior.STRATEGIC, "pol1", satisfaction=0.1)
        assert decide_withdrawal(c, tick=10, term_length=48) is False  # too early
        assert decide_withdrawal(c, tick=30, term_length=48) is True   # late term (>60%)

    def test_strategic_respects_once_constraint(self):
        c = CitizenState("c1", CitizenBehavior.STRATEGIC, "pol1", satisfaction=0.1)
        assert decide_withdrawal(c, tick=30, term_length=48) is True
        execute_withdrawal(c, tick=30)
        assert decide_withdrawal(c, tick=35, term_length=48) is False


class TestExecuteWithdrawal:
    def test_execute_sets_flags(self):
        c = CitizenState("c1", CitizenBehavior.RATIONAL, "pol1")
        execute_withdrawal(c, tick=15)
        assert c.has_withdrawn is True
        assert c.withdrawn_tick == 15

    def test_double_withdrawal_raises(self):
        c = CitizenState("c1", CitizenBehavior.RATIONAL, "pol1", has_withdrawn=True)
        with pytest.raises(ValueError, match="already withdrawn"):
            execute_withdrawal(c, tick=20)
