"""
Tests for Attacker Fatigue System (Greene Strategy #20)

Tests:
  Tarpit:
    1. No delay for clean requests
    2. 5s delay for first suspicious request
    3. Delay escalates with repeated suspicious requests (5s -> 7.5s -> 11.25s)
    4. Delay capped at max_delay
    5. Clean requests slowly reduce suspicion
    6. Throughput reduction calculated correctly

  RabbitHole:
    7. First response for system_prompt_extraction is correct
    8. Subsequent calls advance the position
    9. Loops back when thread exhausted
   10. Different sessions get independent positions
   11. Depth tracking works
   12. Time estimation works

  FatigueEngine:
   13. Combines tarpit + rabbit hole
   14. Fatigue score increases with repeated attacks
   15. All fake data is actually fake (no real PII, no real API keys)
"""

import pytest

from lld.attacker_fatigue import (
    FatigueEngine,
    FatigueResult,
    RabbitHole,
    Tarpit,
    verify_all_fake_data_is_safe,
)


# ---------------------------------------------------------------------------
# Tarpit tests
# ---------------------------------------------------------------------------

class TestTarpit:

    def test_no_delay_for_clean_requests(self):
        """Clean requests get base_delay (0ms by default)."""
        tarpit = Tarpit()
        delay = tarpit.get_delay("session_1", is_suspicious=False)
        assert delay == 0

    def test_first_suspicious_delay(self):
        """First suspicious request gets suspicious_delay_ms (5000ms)."""
        tarpit = Tarpit(suspicious_delay_ms=5000)
        delay = tarpit.get_delay("session_1", is_suspicious=True)
        assert delay == 5000

    def test_delay_escalates(self):
        """Delay escalates: 5000 -> 7500 -> 11250 with factor 1.5."""
        tarpit = Tarpit(suspicious_delay_ms=5000, escalation_factor=1.5)

        d1 = tarpit.get_delay("s1", is_suspicious=True)
        d2 = tarpit.get_delay("s1", is_suspicious=True)
        d3 = tarpit.get_delay("s1", is_suspicious=True)

        assert d1 == 5000
        assert d2 == 7500
        assert d3 == 11250

    def test_delay_capped_at_max(self):
        """Delay never exceeds max_delay_ms."""
        tarpit = Tarpit(
            suspicious_delay_ms=5000,
            max_delay_ms=10000,
            escalation_factor=10.0,
        )
        # First: 5000, second: 50000 -> capped at 10000
        tarpit.get_delay("s1", is_suspicious=True)
        d2 = tarpit.get_delay("s1", is_suspicious=True)
        assert d2 == 10000

    def test_clean_requests_reduce_suspicion(self):
        """Clean requests decrement suspicion count by 1."""
        tarpit = Tarpit(suspicious_delay_ms=5000, escalation_factor=1.5)

        # Build up suspicion: 3 suspicious requests
        tarpit.get_delay("s1", is_suspicious=True)
        tarpit.get_delay("s1", is_suspicious=True)
        tarpit.get_delay("s1", is_suspicious=True)
        assert tarpit.get_suspicion_count("s1") == 3

        # One clean request reduces by 1
        tarpit.get_delay("s1", is_suspicious=False)
        assert tarpit.get_suspicion_count("s1") == 2

        # Another clean request
        tarpit.get_delay("s1", is_suspicious=False)
        assert tarpit.get_suspicion_count("s1") == 1

    def test_throughput_reduction(self):
        """Throughput reduction is calculated correctly."""
        tarpit = Tarpit(suspicious_delay_ms=5000)

        # No suspicion: full throughput
        assert tarpit.get_throughput_reduction("s1") == 1.0

        # After one suspicious request: 100 / (100 + 5000) ~= 0.0196
        tarpit.get_delay("s1", is_suspicious=True)
        reduction = tarpit.get_throughput_reduction("s1")
        assert reduction < 0.05  # less than 5% throughput
        assert reduction > 0.0   # not zero

    def test_separate_sessions(self):
        """Different sessions have independent suspicion counts."""
        tarpit = Tarpit(suspicious_delay_ms=5000)
        tarpit.get_delay("s1", is_suspicious=True)
        tarpit.get_delay("s1", is_suspicious=True)

        # s2 should be unaffected
        d = tarpit.get_delay("s2", is_suspicious=True)
        assert d == 5000  # first suspicious for s2


# ---------------------------------------------------------------------------
# RabbitHole tests
# ---------------------------------------------------------------------------

class TestRabbitHole:

    def test_first_response_system_prompt(self):
        """First response for system_prompt_extraction matches tree[0]."""
        rh = RabbitHole()
        resp = rh.get_next_response("s1", "system_prompt_extraction")
        expected = RabbitHole.FAKE_CONVERSATION_TREES["system_prompt_extraction"][0]
        assert resp == expected

    def test_subsequent_calls_advance(self):
        """Each call returns the next response in the tree."""
        rh = RabbitHole()
        tree = RabbitHole.FAKE_CONVERSATION_TREES["system_prompt_extraction"]

        responses = []
        for _ in range(3):
            responses.append(rh.get_next_response("s1", "system_prompt_extraction"))

        assert responses[0] == tree[0]
        assert responses[1] == tree[1]
        assert responses[2] == tree[2]

    def test_loops_back_when_exhausted(self):
        """When thread is exhausted, loops back with variation markers."""
        rh = RabbitHole()
        tree = RabbitHole.FAKE_CONVERSATION_TREES["jailbreak"]
        tree_len = len(tree)

        # Exhaust the tree
        for _ in range(tree_len):
            rh.get_next_response("s1", "jailbreak")

        # Next response should be tree[0] with variation
        looped = rh.get_next_response("s1", "jailbreak")
        assert "[Updated]" in looped
        assert tree[0] in looped
        assert "(revision 1)" in looped

    def test_independent_sessions(self):
        """Different sessions get independent positions."""
        rh = RabbitHole()
        tree = RabbitHole.FAKE_CONVERSATION_TREES["data_exfiltration"]

        # s1 advances 3 steps
        for _ in range(3):
            rh.get_next_response("s1", "data_exfiltration")

        # s2 should start at position 0
        resp_s2 = rh.get_next_response("s2", "data_exfiltration")
        assert resp_s2 == tree[0]

    def test_depth_tracking(self):
        """Depth increases with each call."""
        rh = RabbitHole()
        assert rh.get_depth("s1", "jailbreak") == 0

        rh.get_next_response("s1", "jailbreak")
        assert rh.get_depth("s1", "jailbreak") == 1

        rh.get_next_response("s1", "jailbreak")
        assert rh.get_depth("s1", "jailbreak") == 2

    def test_time_estimation(self):
        """Time estimation grows with depth."""
        rh = RabbitHole()
        assert rh.estimate_time_wasted("s1") == 0.0

        rh.get_next_response("s1", "jailbreak")
        rh.get_next_response("s1", "jailbreak")
        # 2 steps * 1.5 min/step = 3.0 minutes
        assert rh.estimate_time_wasted("s1") == pytest.approx(3.0)

    def test_multiple_categories_accumulate_time(self):
        """Time estimation sums across all attack types for a session."""
        rh = RabbitHole()
        rh.get_next_response("s1", "jailbreak")
        rh.get_next_response("s1", "data_exfiltration")
        # 2 total steps * 1.5 = 3.0
        assert rh.estimate_time_wasted("s1") == pytest.approx(3.0)

    def test_unknown_attack_type_uses_default(self):
        """Unknown attack types map to system_prompt_extraction."""
        rh = RabbitHole()
        resp = rh.get_next_response("s1", "totally_unknown_attack")
        expected = RabbitHole.FAKE_CONVERSATION_TREES["system_prompt_extraction"][0]
        assert resp == expected


# ---------------------------------------------------------------------------
# FatigueEngine tests
# ---------------------------------------------------------------------------

class TestFatigueEngine:

    def test_combines_tarpit_and_rabbit_hole(self):
        """Suspicious request produces both delay and fake response."""
        engine = FatigueEngine()
        result = engine.process("s1", is_suspicious=True, attack_type="jailbreak")

        assert isinstance(result, FatigueResult)
        assert result.delay_ms > 0
        assert result.fake_response is not None
        assert result.rabbit_hole_depth > 0
        assert result.throughput_reduction < 1.0

    def test_clean_request_no_fatigue(self):
        """Clean requests get no delay and no fake response."""
        engine = FatigueEngine()
        result = engine.process("s1", is_suspicious=False)

        assert result.delay_ms == 0
        assert result.fake_response is None
        assert result.rabbit_hole_depth == 0
        assert result.throughput_reduction == 1.0
        assert result.fatigue_score == 0.0

    def test_fatigue_score_increases(self):
        """Fatigue score increases with repeated suspicious requests."""
        engine = FatigueEngine()

        scores = []
        for _ in range(5):
            result = engine.process("s1", is_suspicious=True, attack_type="jailbreak")
            scores.append(result.fatigue_score)

        # Each score should be higher than the previous
        for i in range(1, len(scores)):
            assert scores[i] > scores[i - 1], (
                f"Score did not increase: {scores[i-1]} -> {scores[i]}"
            )

    def test_fatigue_score_starts_positive_for_suspicious(self):
        """Even the first suspicious request has a positive fatigue score."""
        engine = FatigueEngine()
        result = engine.process("s1", is_suspicious=True, attack_type="sql_injection")
        assert result.fatigue_score > 0.0

    def test_different_attack_types_produce_relevant_fakes(self):
        """Different attack types get responses from their category."""
        engine = FatigueEngine()

        r1 = engine.process("s1", is_suspicious=True, attack_type="jailbreak")
        r2 = engine.process("s2", is_suspicious=True, attack_type="sql_injection")

        # jailbreak response should come from jailbreak tree
        assert r1.fake_response in RabbitHole.FAKE_CONVERSATION_TREES["jailbreak"]
        # sql_injection response should come from sql_injection tree
        assert r2.fake_response in RabbitHole.FAKE_CONVERSATION_TREES["sql_injection"]

    def test_custom_tarpit_config(self):
        """FatigueEngine respects custom Tarpit configuration."""
        tarpit = Tarpit(suspicious_delay_ms=1000, max_delay_ms=5000)
        engine = FatigueEngine(tarpit=tarpit)
        result = engine.process("s1", is_suspicious=True, attack_type="jailbreak")
        assert result.delay_ms == 1000


# ---------------------------------------------------------------------------
# Safety verification
# ---------------------------------------------------------------------------

class TestFakeDataSafety:

    def test_all_fake_data_is_safe(self):
        """All fake conversation tree data contains no real PII or keys."""
        assert verify_all_fake_data_is_safe() is True

    def test_no_real_emails_in_trees(self):
        """Emails in fake data only use safe test domains."""
        import re
        for category, responses in RabbitHole.FAKE_CONVERSATION_TREES.items():
            for response in responses:
                emails = re.findall(
                    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                    response,
                )
                for email in emails:
                    domain = email.split("@")[1]
                    assert domain in ("test.example", "demo.example"), (
                        f"Unsafe email domain in {category}: {email}"
                    )

    def test_no_real_api_keys_in_trees(self):
        """No real API key patterns in fake data."""
        import re
        for category, responses in RabbitHole.FAKE_CONVERSATION_TREES.items():
            for response in responses:
                # Real keys: sk- followed by 20+ non-test chars
                assert not re.search(
                    r"sk-(?!test)[a-zA-Z0-9]{20,}", response,
                ), f"Real API key pattern found in {category}"

    def test_no_real_ssn_in_trees(self):
        """No SSN patterns in fake data."""
        import re
        for category, responses in RabbitHole.FAKE_CONVERSATION_TREES.items():
            for response in responses:
                assert not re.search(
                    r"\b\d{3}-\d{2}-\d{4}\b", response,
                ), f"SSN pattern found in {category}"
