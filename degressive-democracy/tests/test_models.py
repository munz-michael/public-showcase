"""Tests for core data models."""

import math

from degressive_democracy.models import (
    CitizenBehavior,
    CitizenState,
    PoliticianBehavior,
    PoliticianState,
    PowerModel,
    Promise,
    PromiseCategory,
    PromiseState,
    PromiseStatus,
    Vote,
    compute_power,
)


class TestVote:
    def test_active_vote(self):
        v = Vote("c1", "pol1", cast_tick=0)
        assert v.is_active is True

    def test_withdrawn_vote(self):
        v = Vote("c1", "pol1", cast_tick=0, withdrawn_tick=10)
        assert v.is_active is False

    def test_vote_is_frozen(self):
        v = Vote("c1", "pol1")
        try:
            v.citizen_id = "c2"  # type: ignore
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass


class TestPromise:
    def test_promise_is_frozen(self):
        p = Promise("p1", PromiseCategory.ECONOMIC, "Tax", 0.5, 0.8)
        try:
            p.difficulty = 0.9  # type: ignore
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass

    def test_promise_fields(self):
        p = Promise("p1", PromiseCategory.SOCIAL, "Health", 0.7, 0.9, deadline_tick=24)
        assert p.promise_id == "p1"
        assert p.category == PromiseCategory.SOCIAL
        assert p.difficulty == 0.7
        assert p.visibility == 0.9
        assert p.deadline_tick == 24


class TestPromiseState:
    def test_default_state(self):
        ps = PromiseState("p1")
        assert ps.status == PromiseStatus.PENDING
        assert ps.progress == 0.0
        assert ps.effort_invested == 0.0

    def test_mutable(self):
        ps = PromiseState("p1")
        ps.status = PromiseStatus.PROGRESSING
        ps.progress = 0.5
        assert ps.status == PromiseStatus.PROGRESSING
        assert ps.progress == 0.5


class TestCitizenState:
    def test_default_not_withdrawn(self):
        c = CitizenState("c1", CitizenBehavior.RATIONAL, "pol1")
        assert c.has_withdrawn is False
        assert c.withdrawn_tick is None

    def test_all_behaviors_exist(self):
        assert len(CitizenBehavior) == 6


class TestPoliticianState:
    def test_default_full_power(self):
        p = PoliticianState("pol1", PoliticianBehavior.PROMISE_KEEPER)
        assert p.power == 1.0

    def test_all_behaviors_exist(self):
        assert len(PoliticianBehavior) == 5


class TestComputePower:
    def test_linear_full(self):
        assert compute_power(100, 100, PowerModel.LINEAR) == 1.0

    def test_linear_half(self):
        assert compute_power(50, 100, PowerModel.LINEAR) == 0.5

    def test_linear_zero(self):
        assert compute_power(0, 100, PowerModel.LINEAR) == 0.0

    def test_threshold_full(self):
        assert compute_power(80, 100, PowerModel.THRESHOLD) == 1.0

    def test_threshold_mid(self):
        assert compute_power(60, 100, PowerModel.THRESHOLD) == 0.6

    def test_threshold_low(self):
        assert compute_power(30, 100, PowerModel.THRESHOLD) == 0.2

    def test_threshold_zero(self):
        assert compute_power(10, 100, PowerModel.THRESHOLD) == 0.0

    def test_convex_half(self):
        assert compute_power(50, 100, PowerModel.CONVEX) == 0.25

    def test_convex_full(self):
        assert compute_power(100, 100, PowerModel.CONVEX) == 1.0

    def test_logarithmic_full(self):
        result = compute_power(100, 100, PowerModel.LOGARITHMIC)
        assert abs(result - 1.0) < 0.01

    def test_logarithmic_half(self):
        result = compute_power(50, 100, PowerModel.LOGARITHMIC)
        assert 0.5 < result < 1.0  # log is concave

    def test_logarithmic_zero(self):
        assert compute_power(0, 100, PowerModel.LOGARITHMIC) == 0.0

    def test_zero_initial_votes(self):
        assert compute_power(0, 0, PowerModel.LINEAR) == 0.0

    def test_all_power_models(self):
        """Ensure all power models produce values in [0, 1]."""
        for model in PowerModel:
            for votes in [0, 25, 50, 75, 100]:
                power = compute_power(votes, 100, model)
                assert 0.0 <= power <= 1.0, f"{model.value}: power={power} for {votes}/100"
