"""Tests for the Stigmergy (pheromone signals) module."""

from __future__ import annotations

from akm.stigmergy.signals import PheromoneSignal, SignalType, StigmergyNetwork


def test_emit_and_read_signal(db):
    """Emitting a signal should make it readable."""
    network = StigmergyNetwork(db)

    signal = PheromoneSignal(
        signal_type=SignalType.THREAT_DETECTED,
        domain="python",
        intensity=0.7,
        source_component="immune",
        source_id=42,
        metadata="hallucination",
    )
    sid = network.emit(signal)
    assert sid > 0

    signals = network.read_signals(domain="python")
    assert len(signals) == 1
    assert signals[0]["signal_type"] == "threat_detected"
    assert signals[0]["domain"] == "python"
    assert signals[0]["effective_intensity"] > 0.5


def test_signal_reinforcement(db):
    """Emitting the same signal type+domain should reinforce, not duplicate."""
    network = StigmergyNetwork(db)

    sig = PheromoneSignal(
        signal_type=SignalType.THREAT_DETECTED,
        domain="react",
        intensity=0.5,
        source_component="immune",
    )
    id1 = network.emit(sig)
    id2 = network.emit(sig)

    # Should reinforce same signal, not create new
    assert id1 == id2

    signals = network.read_signals(domain="react")
    assert len(signals) == 1
    # Intensity should be boosted
    assert signals[0]["intensity"] > 0.5
    assert signals[0]["reinforcement_count"] == 1


def test_domain_threat_level(db):
    """Domain threat level aggregates threat signals."""
    network = StigmergyNetwork(db)

    # No signals = 0 threat
    assert network.get_domain_threat_level("unknown") == 0.0

    # Add threat signal
    network.emit(PheromoneSignal(
        signal_type=SignalType.THREAT_DETECTED,
        domain="docker",
        intensity=0.6,
        source_component="immune",
    ))
    level = network.get_domain_threat_level("docker")
    assert level > 0.0

    # Non-threat signal should not affect threat level
    network.emit(PheromoneSignal(
        signal_type=SignalType.NUTRIENT_RICH,
        domain="docker",
        intensity=0.9,
        source_component="composting",
    ))
    level2 = network.get_domain_threat_level("docker")
    assert abs(level2 - level) < 1e-6  # nutrient signal doesn't affect threat level


def test_different_domains_independent(db):
    """Signals in different domains are independent."""
    network = StigmergyNetwork(db)

    network.emit(PheromoneSignal(
        signal_type=SignalType.THREAT_DETECTED,
        domain="python",
        intensity=0.8,
        source_component="immune",
    ))
    network.emit(PheromoneSignal(
        signal_type=SignalType.DOMAIN_HEALTHY,
        domain="rust",
        intensity=0.9,
        source_component="immune",
    ))

    python_signals = network.read_signals(domain="python")
    rust_signals = network.read_signals(domain="rust")

    assert len(python_signals) == 1
    assert len(rust_signals) == 1
    assert python_signals[0]["signal_type"] == "threat_detected"
    assert rust_signals[0]["signal_type"] == "domain_healthy"


def test_stats(db):
    """Stats should summarize the signal landscape."""
    network = StigmergyNetwork(db)

    network.emit(PheromoneSignal(
        signal_type=SignalType.THREAT_DETECTED,
        domain="python",
        intensity=0.5,
        source_component="immune",
    ))
    network.emit(PheromoneSignal(
        signal_type=SignalType.HIGH_ENTROPY,
        domain="javascript",
        intensity=0.6,
        source_component="composting",
    ))

    stats = network.get_stats()
    assert stats["active_signals"] == 2
    assert "threat_detected" in stats["by_type"]
    assert "high_entropy" in stats["by_type"]
    assert set(stats["active_domains"]) == {"python", "javascript"}
