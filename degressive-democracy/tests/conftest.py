"""Shared fixtures for degressive democracy tests."""

import pytest

from degressive_democracy.models import (
    CitizenBehavior,
    CitizenState,
    ElectionConfig,
    PoliticianBehavior,
    PoliticianState,
    Promise,
    PromiseCategory,
    PromiseState,
    PromiseStatus,
    PowerModel,
    Vote,
)


@pytest.fixture
def basic_promise():
    return Promise(
        promise_id="p1",
        category=PromiseCategory.ECONOMIC,
        description="Lower taxes",
        difficulty=0.5,
        visibility=0.8,
    )


@pytest.fixture
def basic_promises():
    return [
        Promise("p1", PromiseCategory.ECONOMIC, "Lower taxes", 0.5, 0.8),
        Promise("p2", PromiseCategory.SOCIAL, "Better healthcare", 0.7, 0.9),
        Promise("p3", PromiseCategory.ENVIRONMENTAL, "Green energy", 0.6, 0.5),
        Promise("p4", PromiseCategory.INFRASTRUCTURE, "New roads", 0.4, 0.3),
        Promise("p5", PromiseCategory.SECURITY, "More police", 0.3, 0.6),
    ]


@pytest.fixture
def basic_politician(basic_promises):
    pol = PoliticianState(
        politician_id="pol1",
        behavior=PoliticianBehavior.PROMISE_KEEPER,
        promises=basic_promises,
        initial_votes=200,
        current_votes=200,
    )
    pol.promise_states = {
        p.promise_id: PromiseState(promise_id=p.promise_id)
        for p in basic_promises
    }
    return pol


@pytest.fixture
def rational_citizen():
    return CitizenState(
        citizen_id="c1",
        behavior=CitizenBehavior.RATIONAL,
        politician_id="pol1",
        satisfaction=1.0,
        withdrawal_threshold=0.4,
    )


@pytest.fixture
def default_config():
    return ElectionConfig(
        n_citizens=100,
        n_politicians=2,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=42,
    )
