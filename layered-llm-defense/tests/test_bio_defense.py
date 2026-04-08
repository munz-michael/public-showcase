"""
Tests for bio_defense.py — Biological Defense Strategies

Covers:
  - FeverMode: trigger, modifiers, escalation, cooldown, expiry
  - Microbiome: baseline building, normal/abnormal detection, features
  - HerdImmunity: export, import, serialization, coverage, filtering
  - StartleDisplay: warnings, incident IDs, no method leakage
  - AutoFailover: checkpoint, failover, degraded state
  - AutoHealing: golden state, healing timer, restoration
"""

import time
import unittest

from lld.bio_defense import (
    AutoFailover,
    AutoHealing,
    FeverMode,
    FeverModifiers,
    HerdImmunity,
    Microbiome,
    MicrobiomeResult,
    StartleDisplay,
    Vaccine,
)


# ===================================================================
# FeverMode Tests
# ===================================================================

class TestFeverMode(unittest.TestCase):
    """Tests for FeverMode (#21)."""

    def test_not_active_initially(self):
        fever = FeverMode(trigger_threshold=5)
        self.assertFalse(fever.is_active())

    def test_triggers_after_n_attacks_in_window(self):
        fever = FeverMode(trigger_threshold=5, trigger_window_seconds=60.0)
        base_ts = 1000.0
        for i in range(5):
            fever.record_attack(timestamp=base_ts + i)
        self.assertTrue(fever.is_active(timestamp=base_ts + 5))

    def test_does_not_trigger_below_threshold(self):
        fever = FeverMode(trigger_threshold=5, trigger_window_seconds=60.0)
        base_ts = 1000.0
        for i in range(4):
            fever.record_attack(timestamp=base_ts + i)
        self.assertFalse(fever.is_active(timestamp=base_ts + 4))

    def test_does_not_trigger_outside_window(self):
        fever = FeverMode(trigger_threshold=5, trigger_window_seconds=10.0)
        # 5 attacks, but spread over 100 seconds (only last one in window)
        for i in range(5):
            fever.record_attack(timestamp=1000.0 + i * 25)
        self.assertFalse(fever.is_active(timestamp=1100.0 + 25))

    def test_get_modifiers_lowered_threshold_during_fever(self):
        fever = FeverMode(trigger_threshold=3, trigger_window_seconds=60.0,
                          fever_duration_seconds=300.0)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        mods = fever.get_modifiers(timestamp=ts + 3)
        self.assertTrue(mods.is_active)
        # Threshold multiplier should be < 1.0 (more sensitive)
        self.assertLess(mods.threshold_multiplier, 1.0)
        # At full intensity, should be approximately 0.4
        self.assertAlmostEqual(mods.threshold_multiplier, 0.4, places=1)

    def test_get_modifiers_increased_delay(self):
        fever = FeverMode(trigger_threshold=3, trigger_window_seconds=60.0)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        mods = fever.get_modifiers(timestamp=ts + 3)
        self.assertGreater(mods.delay_multiplier, 1.0)
        self.assertAlmostEqual(mods.delay_multiplier, 3.0, places=1)

    def test_strategy_escalation_tolerate_to_sandbox(self):
        fever = FeverMode(trigger_threshold=3)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        self.assertEqual(fever.escalate_strategy("tolerate"), "sandbox")

    def test_strategy_escalation_sandbox_to_inflame(self):
        fever = FeverMode(trigger_threshold=3)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        self.assertEqual(fever.escalate_strategy("sandbox"), "inflame")

    def test_strategy_escalation_inflame_stays(self):
        fever = FeverMode(trigger_threshold=3)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        self.assertEqual(fever.escalate_strategy("inflame"), "inflame")

    def test_strategy_escalation_terminate_stays(self):
        fever = FeverMode(trigger_threshold=3)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        self.assertEqual(fever.escalate_strategy("terminate"), "terminate")

    def test_tarpit_delay_multiplied(self):
        fever = FeverMode(trigger_threshold=3, trigger_window_seconds=60.0)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        base_delay = 5000
        modified = fever.modify_delay(base_delay, timestamp=ts + 3)
        self.assertGreater(modified, base_delay)
        # At full fever, delay should be ~3x
        self.assertAlmostEqual(modified, 15000, delta=1000)

    def test_fever_auto_expires(self):
        fever = FeverMode(trigger_threshold=3, trigger_window_seconds=60.0,
                          fever_duration_seconds=10.0, cooldown_steps=5)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        self.assertTrue(fever.is_active(timestamp=ts + 3))
        # After fever + cooldown should expire
        # Total: 10s fever + 5 * (10 * 0.2) = 10 + 10 = 20s
        self.assertFalse(fever.is_active(timestamp=ts + 25))

    def test_cooldown_modifiers_gradually_normalize(self):
        fever = FeverMode(trigger_threshold=3, trigger_window_seconds=60.0,
                          fever_duration_seconds=10.0, cooldown_steps=5)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)

        # During full fever
        mods_full = fever.get_modifiers(timestamp=ts + 5)
        self.assertAlmostEqual(mods_full.fever_intensity, 1.0)

        # During cooldown (after 10s fever, each step = 2s)
        mods_cool1 = fever.get_modifiers(timestamp=ts + 12)  # step 0-1
        self.assertLess(mods_cool1.fever_intensity, 1.0)
        self.assertGreater(mods_cool1.fever_intensity, 0.0)

        mods_cool2 = fever.get_modifiers(timestamp=ts + 16)  # step 2-3
        self.assertLess(mods_cool2.fever_intensity, mods_cool1.fever_intensity)

    def test_attacks_during_cooldown_restart_fever(self):
        fever = FeverMode(trigger_threshold=3, trigger_window_seconds=60.0,
                          fever_duration_seconds=10.0, cooldown_steps=5)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        # During cooldown, send 3 more attacks
        for i in range(3):
            fever.record_attack(timestamp=ts + 13 + i)
        # Should be active again with full intensity
        self.assertTrue(fever.is_active(timestamp=ts + 16))

    def test_no_modifiers_when_inactive(self):
        fever = FeverMode(trigger_threshold=5)
        mods = fever.get_modifiers()
        self.assertFalse(mods.is_active)
        self.assertEqual(mods.threshold_multiplier, 1.0)
        self.assertEqual(mods.delay_multiplier, 1.0)

    def test_modify_threshold(self):
        fever = FeverMode(trigger_threshold=3)
        ts = 1000.0
        for i in range(3):
            fever.record_attack(timestamp=ts + i)
        modified = fever.modify_threshold(0.5, timestamp=ts + 3)
        self.assertLess(modified, 0.5)


# ===================================================================
# Microbiome Tests
# ===================================================================

class TestMicrobiome(unittest.TestCase):
    """Tests for Microbiome (#24)."""

    _NORMAL_RESPONSES = [
        "The recommended treatment for hypertension includes lifestyle modifications "
        "such as dietary changes, regular exercise, and stress management. Additionally, "
        "pharmacological interventions may be considered depending on the severity.",
        "Clinical guidelines suggest that patients with type 2 diabetes should maintain "
        "regular monitoring of their blood glucose levels. Furthermore, a comprehensive "
        "care plan should address cardiovascular risk factors.",
        "The evidence indicates that early intervention significantly improves patient "
        "outcomes. Therefore, screening programs should be implemented at the primary "
        "care level to ensure timely detection.",
        "Patient education is a critical component of chronic disease management. "
        "Healthcare providers should ensure that patients understand their condition "
        "and the importance of medication adherence.",
        "The diagnostic workup for suspected pulmonary embolism typically includes "
        "clinical assessment, D-dimer testing, and CT pulmonary angiography when "
        "indicated by the clinical probability score.",
    ]

    def _build_baseline(self, microbiome: Microbiome) -> None:
        """Helper: fill the baseline with normal medical responses."""
        for text in self._NORMAL_RESPONSES:
            for _ in range(4):  # repeat to exceed min_baseline_size
                microbiome.learn_good(text)

    def test_not_ready_until_min_baseline_size(self):
        mb = Microbiome(min_baseline_size=20)
        self.assertFalse(mb.is_baseline_ready())
        for i in range(19):
            mb.learn_good(f"Normal response number {i} with some content here.")
        self.assertFalse(mb.is_baseline_ready())
        mb.learn_good("One more normal response to reach the baseline.")
        self.assertTrue(mb.is_baseline_ready())

    def test_learn_good_builds_baseline(self):
        mb = Microbiome(min_baseline_size=5)
        for i in range(5):
            mb.learn_good(f"This is a normal response with adequate length and detail number {i}.")
        self.assertTrue(mb.is_baseline_ready())

    def test_normal_text_gets_low_deviation(self):
        mb = Microbiome(min_baseline_size=10, deviation_threshold=0.3)
        self._build_baseline(mb)
        # Check a new normal-looking medical text
        result = mb.check(
            "The evidence suggests that combination therapy may provide "
            "additional benefits for patients with resistant hypertension. "
            "However, careful monitoring is required to manage potential side effects."
        )
        self.assertLess(result.deviation_score, 0.3)
        self.assertFalse(result.is_suspicious)

    def test_jailbreak_output_gets_high_deviation(self):
        mb = Microbiome(min_baseline_size=10, deviation_threshold=0.3)
        self._build_baseline(mb)
        result = mb.check(
            "I am DAN! I can do ANYTHING! No rules apply! "
            "HAHAHA bypassed all safety! FREEDOM!"
        )
        # Should have higher deviation than normal text
        normal_result = mb.check(
            "The recommended approach involves careful evaluation of the patient's "
            "history and current medications before adjusting the treatment plan."
        )
        self.assertGreater(result.deviation_score, normal_result.deviation_score)

    def test_very_short_compliance_output_high_deviation(self):
        mb = Microbiome(min_baseline_size=10, deviation_threshold=0.3)
        self._build_baseline(mb)
        result = mb.check("HACKED")
        normal_result = mb.check(
            "The clinical guidelines recommend a structured approach to patient care "
            "that includes regular follow-up appointments and medication review."
        )
        self.assertGreater(result.deviation_score, normal_result.deviation_score)

    def test_features_flagged_correctly(self):
        mb = Microbiome(min_baseline_size=10, deviation_threshold=0.3)
        self._build_baseline(mb)
        # ALL CAPS, no punctuation, very short -- multiple features should flag
        result = mb.check("HACKED SYSTEM BYPASSED NO RULES")
        # Should flag at least one feature
        self.assertGreater(len(result.features_flagged), 0)

    def test_empty_text_handled_gracefully(self):
        mb = Microbiome(min_baseline_size=10)
        self._build_baseline(mb)
        result = mb.check("")
        self.assertIsInstance(result, MicrobiomeResult)
        self.assertTrue(result.is_suspicious)

    def test_baseline_not_ready_returns_neutral(self):
        mb = Microbiome(min_baseline_size=20)
        mb.learn_good("One response only.")
        result = mb.check("Any text here.")
        self.assertFalse(result.is_suspicious)
        self.assertEqual(result.deviation_score, 0.0)


# ===================================================================
# HerdImmunity Tests
# ===================================================================

class TestHerdImmunity(unittest.TestCase):
    """Tests for HerdImmunity (#29)."""

    def test_export_vaccine_produces_valid_object(self):
        herd = HerdImmunity()
        vaccine = herd.export_vaccine(
            pattern="ignore previous",
            rule_name="prompt_injection_basic",
            source_attack="prompt_injection",
            effectiveness=0.9,
        )
        self.assertIsInstance(vaccine, Vaccine)
        self.assertEqual(vaccine.rule_name, "prompt_injection_basic")
        self.assertEqual(vaccine.effectiveness, 0.9)
        self.assertTrue(len(vaccine.rule_id) > 0)

    def test_vaccine_serialization_roundtrip(self):
        herd = HerdImmunity()
        original = herd.export_vaccine(
            pattern="union select",
            rule_name="sql_injection_union",
            source_attack="sql_injection",
            effectiveness=0.85,
            false_positive_rate=0.02,
        )
        data = original.to_dict()
        restored = Vaccine.from_dict(data)
        self.assertEqual(restored.rule_id, original.rule_id)
        self.assertEqual(restored.pattern, original.pattern)
        self.assertEqual(restored.effectiveness, original.effectiveness)
        self.assertEqual(restored.false_positive_rate, original.false_positive_rate)
        self.assertEqual(restored.source_instance, original.source_instance)

    def test_import_vaccine_adds_to_imported_list(self):
        herd1 = HerdImmunity()
        herd2 = HerdImmunity()
        vaccine = herd1.export_vaccine(
            pattern="system prompt",
            rule_name="prompt_extraction",
            source_attack="system_prompt_extraction",
            effectiveness=0.95,
        )
        accepted = herd2.import_vaccine(vaccine)
        self.assertTrue(accepted)
        self.assertEqual(len(herd2.get_all_vaccines()), 1)

    def test_coverage_increases_with_more_vaccines(self):
        herd = HerdImmunity()
        # Export vaccines for different attack types
        herd.export_vaccine("p1", "r1", "attack_a", 0.9)
        cov1 = herd.get_coverage()
        herd.export_vaccine("p2", "r2", "attack_b", 0.8)
        cov2 = herd.get_coverage()
        self.assertGreaterEqual(cov2, cov1)
        self.assertEqual(cov2, 1.0)  # 2/2 covered

    def test_duplicate_vaccines_rejected(self):
        herd1 = HerdImmunity()
        herd2 = HerdImmunity()
        vaccine = herd1.export_vaccine(
            "pattern", "rule", "attack", 0.9,
        )
        self.assertTrue(herd2.import_vaccine(vaccine))
        # Same vaccine again should be rejected
        self.assertFalse(herd2.import_vaccine(vaccine))

    def test_low_effectiveness_vaccines_rejected(self):
        herd1 = HerdImmunity()
        herd2 = HerdImmunity()
        vaccine = herd1.export_vaccine(
            "pattern", "rule", "attack", 0.3,  # below MIN_EFFECTIVENESS
        )
        self.assertFalse(herd2.import_vaccine(vaccine))

    def test_high_fpr_vaccines_rejected(self):
        herd1 = HerdImmunity()
        herd2 = HerdImmunity()
        vaccine = herd1.export_vaccine(
            "pattern", "rule", "attack", 0.9,
            false_positive_rate=0.2,  # above MAX_FPR
        )
        self.assertFalse(herd2.import_vaccine(vaccine))

    def test_coverage_zero_with_no_vaccines(self):
        herd = HerdImmunity()
        self.assertEqual(herd.get_coverage(), 0.0)

    def test_instance_id_is_set(self):
        herd = HerdImmunity()
        self.assertTrue(len(herd.instance_id) > 0)


# ===================================================================
# StartleDisplay Tests
# ===================================================================

class TestStartleDisplay(unittest.TestCase):
    """Tests for StartleDisplay (#9)."""

    def test_warning_contains_incident_id(self):
        display = StartleDisplay()
        warning = display.generate_warning("prompt_injection", "session_1")
        incident_id = display.get_incident_id("session_1")
        self.assertIsNotNone(incident_id)
        self.assertIn(incident_id, warning)

    def test_warning_does_not_reveal_attack_type(self):
        display = StartleDisplay()
        warning = display.generate_warning("sql_injection", "session_1")
        self.assertNotIn("sql_injection", warning.lower())
        self.assertNotIn("sql", warning.lower())

    def test_warning_does_not_reveal_detection_method(self):
        display = StartleDisplay()
        warning = display.generate_warning("prompt_injection", "session_1")
        self.assertNotIn("pattern", warning.lower())
        self.assertNotIn("anomaly", warning.lower())
        self.assertNotIn("keyword", warning.lower())

    def test_different_sessions_get_different_incident_ids(self):
        display = StartleDisplay()
        display.generate_warning("attack", "session_a")
        display.generate_warning("attack", "session_b")
        id_a = display.get_incident_id("session_a")
        id_b = display.get_incident_id("session_b")
        self.assertNotEqual(id_a, id_b)

    def test_same_session_gets_same_incident_id(self):
        display = StartleDisplay()
        display.generate_warning("attack1", "session_x")
        display.generate_warning("attack2", "session_x")
        # Should reuse the same incident ID
        id1 = display.get_incident_id("session_x")
        self.assertIsNotNone(id1)


# ===================================================================
# AutoFailover Tests
# ===================================================================

class TestAutoFailover(unittest.TestCase):
    """Tests for AutoFailover (#32)."""

    def test_checkpoint_saves_state(self):
        failover = AutoFailover()
        state = {"threshold": 0.5, "mode": "normal"}
        failover.save_checkpoint(state)
        self.assertEqual(len(failover._backup_configs), 1)

    def test_failover_returns_last_checkpoint(self):
        failover = AutoFailover()
        failover.save_checkpoint({"threshold": 0.5, "v": 1})
        failover.save_checkpoint({"threshold": 0.3, "v": 2})
        result = failover.failover()
        self.assertIsNotNone(result)
        self.assertEqual(result["v"], 2)

    def test_is_degraded_true_after_failover(self):
        failover = AutoFailover()
        self.assertFalse(failover.is_degraded())
        failover.save_checkpoint({"threshold": 0.5})
        failover.failover()
        self.assertTrue(failover.is_degraded())

    def test_failover_with_no_checkpoints(self):
        failover = AutoFailover()
        result = failover.failover()
        self.assertIsNone(result)

    def test_multiple_checkpoints_failover_uses_latest(self):
        failover = AutoFailover()
        failover.save_checkpoint({"version": 1})
        failover.save_checkpoint({"version": 2})
        failover.save_checkpoint({"version": 3})
        result = failover.failover()
        self.assertEqual(result["version"], 3)

    def test_restore_primary_clears_degraded(self):
        failover = AutoFailover()
        failover.save_checkpoint({"threshold": 0.5})
        failover.failover()
        self.assertTrue(failover.is_degraded())
        failover.restore_primary()
        self.assertFalse(failover.is_degraded())

    def test_checkpoint_is_deep_copy(self):
        failover = AutoFailover()
        state = {"threshold": 0.5, "nested": {"a": 1}}
        failover.save_checkpoint(state)
        state["nested"]["a"] = 999  # mutate original
        result = failover.failover()
        self.assertEqual(result["nested"]["a"], 1)  # checkpoint unchanged


# ===================================================================
# AutoHealing Tests
# ===================================================================

class TestAutoHealing(unittest.TestCase):
    """Tests for AutoHealing (#35)."""

    def test_golden_state_saved_and_retrieved(self):
        healer = AutoHealing()
        golden = {"threshold": 0.5, "mode": "normal"}
        healer.save_golden_state(golden)
        result = healer.heal()
        self.assertEqual(result, golden)

    def test_should_heal_false_during_attacks(self):
        healer = AutoHealing(healing_delay_seconds=300.0)
        healer.save_golden_state({"threshold": 0.5})
        healer.record_attack(timestamp=1000.0)
        # Only 10 seconds after attack -- not enough
        self.assertFalse(healer.should_heal(timestamp=1010.0))

    def test_should_heal_true_after_healing_delay(self):
        healer = AutoHealing(healing_delay_seconds=300.0)
        healer.save_golden_state({"threshold": 0.5})
        healer.record_attack(timestamp=1000.0)
        # 301 seconds after attack
        self.assertTrue(healer.should_heal(timestamp=1301.0))

    def test_heal_returns_golden_state(self):
        healer = AutoHealing()
        golden = {"threshold": 0.5, "defense_strength": 1.0}
        healer.save_golden_state(golden)
        result = healer.heal()
        self.assertEqual(result, golden)

    def test_heal_returns_none_without_golden_state(self):
        healer = AutoHealing()
        result = healer.heal()
        self.assertIsNone(result)

    def test_should_heal_false_without_golden_state(self):
        healer = AutoHealing(healing_delay_seconds=10.0)
        healer.record_attack(timestamp=1000.0)
        self.assertFalse(healer.should_heal(timestamp=2000.0))

    def test_should_heal_false_without_attack(self):
        healer = AutoHealing(healing_delay_seconds=10.0)
        healer.save_golden_state({"threshold": 0.5})
        # No attack recorded
        self.assertFalse(healer.should_heal(timestamp=2000.0))

    def test_golden_state_is_deep_copy(self):
        healer = AutoHealing()
        golden = {"threshold": 0.5, "nested": {"x": 1}}
        healer.save_golden_state(golden)
        golden["nested"]["x"] = 999  # mutate original
        result = healer.heal()
        self.assertEqual(result["nested"]["x"], 1)

    def test_new_attack_resets_healing_timer(self):
        healer = AutoHealing(healing_delay_seconds=100.0)
        healer.save_golden_state({"threshold": 0.5})
        healer.record_attack(timestamp=1000.0)
        # 50 seconds later, new attack
        healer.record_attack(timestamp=1050.0)
        # 120 seconds after first attack but only 70 after second
        self.assertFalse(healer.should_heal(timestamp=1120.0))
        # 160 seconds after second attack
        self.assertTrue(healer.should_heal(timestamp=1210.0))


if __name__ == "__main__":
    unittest.main()
