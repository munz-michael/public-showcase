"""Tests for the Homeostasis (self-regulation) module."""

from __future__ import annotations

from akm.homeostasis.regulator import HomeostasisRegulator, SystemVitals


def test_measure_vitals_empty_db(db):
    """Vitals on empty DB should return zeros."""
    regulator = HomeostasisRegulator(db)
    vitals = regulator.measure_vitals()

    assert vitals.total_chunks == 0
    assert vitals.threat_rate == 0.0
    assert vitals.false_positive_rate == 0.0
    assert vitals.composting_throughput == 0.0
    assert vitals.fermentation_rejection_rate == 0.0


def test_measure_vitals_with_data(seeded_db):
    """Vitals should reflect actual data state."""
    # seeded_db has 5 chunks, 0 scans
    regulator = HomeostasisRegulator(seeded_db)
    vitals = regulator.measure_vitals()

    assert vitals.total_chunks == 5
    assert vitals.threat_rate == 0.0


def test_diagnose_high_threat_rate(db):
    """High threat rate should recommend faster decay."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(
        total_chunks=100,
        threat_rate=0.35,  # way above 0.20 setpoint
    )
    adjustments = regulator.diagnose(vitals)

    param_names = [a.parameter for a in adjustments]
    assert "entropy_decay_rate" in param_names

    adj = next(a for a in adjustments if a.parameter == "entropy_decay_rate")
    assert adj.recommended_value > adj.current_value


def test_diagnose_high_false_positive_rate(db):
    """High FP rate should raise confidence threshold."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(
        total_chunks=100,
        threat_rate=0.10,
        false_positive_rate=0.25,  # above 0.15 setpoint
    )
    adjustments = regulator.diagnose(vitals)

    param_names = [a.parameter for a in adjustments]
    assert "immune_confidence_threshold" in param_names

    adj = next(a for a in adjustments if a.parameter == "immune_confidence_threshold")
    assert adj.recommended_value > adj.current_value


def test_diagnose_high_entropy(db):
    """High average entropy should lower composting threshold."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(
        total_chunks=100,
        avg_entropy=0.6,  # above 0.45 setpoint
    )
    adjustments = regulator.diagnose(vitals)

    param_names = [a.parameter for a in adjustments]
    assert "entropy_threshold" in param_names

    adj = next(a for a in adjustments if a.parameter == "entropy_threshold")
    assert adj.recommended_value < adj.current_value


def test_diagnose_high_rejection_rate(db):
    """High fermentation rejection should extend duration."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(
        total_chunks=100,
        fermentation_rejection_rate=0.45,  # above 0.30 setpoint
    )
    adjustments = regulator.diagnose(vitals)

    param_names = [a.parameter for a in adjustments]
    assert "fermentation_duration_hours" in param_names

    adj = next(a for a in adjustments if a.parameter == "fermentation_duration_hours")
    assert adj.recommended_value > 24.0


def test_diagnose_healthy_system(db):
    """A healthy system should need no adjustments."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(
        total_chunks=100,
        threat_rate=0.10,
        false_positive_rate=0.05,
        composting_throughput=0.05,
        fermentation_rejection_rate=0.15,
        avg_entropy=0.30,
        nutrient_reuse_rate=0.25,
    )
    adjustments = regulator.diagnose(vitals)
    assert len(adjustments) == 0


def test_apply_adjustments(db):
    """Applying adjustments should persist to DB."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(
        total_chunks=100,
        threat_rate=0.35,
    )
    adjustments = regulator.diagnose(vitals)
    results = regulator.apply_adjustments(adjustments)

    assert len(results) > 0

    # Verify persisted
    new_value = regulator.get_param("entropy_decay_rate")
    assert new_value > 0.01  # above default


def test_record_and_retrieve_vitals(db):
    """Recording vitals should create metric history."""
    regulator = HomeostasisRegulator(db)

    vitals = SystemVitals(total_chunks=50, threat_rate=0.12, avg_entropy=0.3)
    regulator.record_vitals(vitals)

    report = regulator.get_health_report()
    assert "total_chunks" in report["trends"]


def test_health_report_status(db):
    """Health report should classify system status."""
    regulator = HomeostasisRegulator(db)

    # Empty DB = healthy (no deviations)
    report = regulator.get_health_report()
    assert report["status"] in ("healthy", "mild_deviation", "needs_attention")


def test_get_param_default(db):
    """get_param should return defaults when no adjustment exists."""
    regulator = HomeostasisRegulator(db)
    assert regulator.get_param("entropy_decay_rate") == 0.01
    assert regulator.get_param("nonexistent", 42.0) == 42.0


def test_domain_specific_params(db):
    """Domain-specific params should override global."""
    regulator = HomeostasisRegulator(db)

    # Set global
    db.execute(
        "INSERT INTO homeostasis_params (parameter, value, domain) VALUES (?, ?, NULL)",
        ("entropy_threshold", 0.7),
    )
    # Set domain-specific
    db.execute(
        "INSERT INTO homeostasis_params (parameter, value, domain) VALUES (?, ?, ?)",
        ("entropy_threshold", 0.5, "docker"),
    )
    db.commit()

    assert regulator.get_param("entropy_threshold") == 0.7
    assert regulator.get_domain_param("entropy_threshold", "docker") == 0.5
    assert regulator.get_domain_param("entropy_threshold", "python") == 0.7  # fallback to global
