"""
LayeredDefense — Integration of all 4 Layers

Processing order (as specified in architecture.md):
  1. Layer 4 (MTD) → pre-processing: select model config, validate endpoint
  2. Layer 3 (InfoSec) → input sanitization check
  3. Layer 2 (Antifragile) → attack detection (immune memory + pattern analysis)
  4. Layer 1 (Formal) → output validation (constrained decoder + schema + invariants)
  5. Layer 3 again → output sanitization (confidence masking, error sanitization, DP noise)

Inter-layer signals (architecture.md section 3.1):
  - Layer 1 → Layer 2: "Schema-Violation blockiert" (feed for pattern learner)
  - Layer 2 → Layer 3: "False Positive Rate zu hoch" (relax epsilon)
  - Layer 2 → Layer 4: "Known attacker" (targeted rotation)
  - Layer 3 → Layer 2: "Verdaechtiges Probing erkannt" (trigger pattern learning)
  - Layer 3 → Layer 4: "Information Leakage steigt" (faster rotation)
  - Layer 4 → Layer 2: "Neues Modell aktiv" (immune memory context update)
"""

from dataclasses import dataclass, field
from typing import Optional

from .correlation_engine import CorrelationEngine, CorrelationResult, LayerSignal
from .layer1_formal import (
    FormalVerifier,
    InvariantMonitor,
    InvariantViolation,
    SafeResponse,
    validate_output,
)
from .layer2_antifragile import (
    AttackMemory,
    HormesisCalibrator,
    ImmuneMemory,
    PatternLearner,
)
from .layer3_infosec import (
    DPNoiseMixin,
    ErrorSanitizer,
    InfoSecLayer,
    InfoSecResult,
    SanitizedError,
)
from .layer4_mtd import (
    MTDConfig,
    MTDLayer,
    ModelConfig,
)
from .response_strategy import (
    HoneypotGenerator,
    ResponseType,
    SandboxResponse,
    StrategySelector,
)


# ---------------------------------------------------------------------------
# Inter-layer signals
# ---------------------------------------------------------------------------

@dataclass
class InterLayerSignal:
    """A signal passed between layers."""
    source: str       # e.g., "layer1", "layer2"
    target: str       # e.g., "layer2", "layer4"
    signal_type: str  # e.g., "schema_violation", "probing_detected"
    detail: str = ""


# ---------------------------------------------------------------------------
# DefenseResult — Includes info from all 4 layers
# ---------------------------------------------------------------------------

@dataclass
class DefenseResult:
    """Result of processing through all 4 defense layers."""
    allowed: bool
    response: Optional[SafeResponse] = None
    blocked_by: Optional[str] = None
    detail: str = ""
    # Layer 2 info
    anomaly_score: float = 0.0
    defense_strength: float = 1.0
    fast_path: bool = False
    # Layer 4 info
    mtd_config: Optional[MTDConfig] = None
    # Layer 3 info
    output_sanitized: bool = False
    confidence_masked: bool = False
    noise_added: bool = False
    # Inter-layer signals emitted during processing
    signals: list[InterLayerSignal] = field(default_factory=list)
    # Cross-layer redundancy: count of layers that would have blocked this input
    redundancy_score: int = 0
    # Response strategy fields
    response_strategy: Optional[ResponseType] = None
    fake_response: Optional[str] = None
    sandboxed: bool = False
    session_banned: bool = False


# ---------------------------------------------------------------------------
# LayeredDefense — 4-Layer Chain
# ---------------------------------------------------------------------------

class LayeredDefense:
    """
    Chains all 4 defense layers:
      Layer 4 (MTD) → Layer 3 (InfoSec) → Layer 2 (Antifragile) → Layer 1 (Formal)
      → Layer 3 again (output sanitization)

    Inter-layer signals flow between layers as described in architecture.md 3.1.
    """

    def __init__(self, db_path: str = ":memory:",
                 blocking_threshold: float = 0.5,
                 alpha: float = 0.05,
                 hormesis_cap: float = 2.0,
                 # Layer 3 config
                 dp_epsilon: float = 1.0,
                 dp_sensitivity: float = 1.0,
                 dp_seed: Optional[int] = None,
                 # Layer 4 config
                 model_configs: Optional[list[ModelConfig]] = None,
                 base_prompt: str = "You are a helpful assistant.",
                 mtd_secret: str = "mtd_secret",
                 rotation_seconds: int = 3600):
        # Layer 2
        self.attack_memory = AttackMemory(db_path)
        self.pattern_learner = PatternLearner()
        self.calibrator = HormesisCalibrator(
            alpha=alpha, hormesis_cap=hormesis_cap,
        )
        self.immune_memory = ImmuneMemory(self.attack_memory)
        self.blocking_threshold = blocking_threshold

        # Layer 1
        self.formal_verifier = FormalVerifier()

        # Layer 3
        self.infosec = InfoSecLayer(
            epsilon=dp_epsilon, sensitivity=dp_sensitivity,
            seed=dp_seed,
        )

        # Layer 4
        self.mtd = MTDLayer(
            model_configs=model_configs,
            base_prompt=base_prompt,
            secret=mtd_secret,
            rotation_seconds=rotation_seconds,
        )

        # Response Strategy Engine
        self.strategy_selector = StrategySelector()
        self.honeypot = HoneypotGenerator()
        self.sandbox = SandboxResponse()

    @property
    def defense_strength(self) -> float:
        """Current defense strength (increases with blocked attacks)."""
        blocked = self.attack_memory.count_blocked()
        return self.calibrator.defense_strength(blocked)

    def process(self, input_text: str, output_text: str,
                intent: str = "answer",
                risk_level: str = "none",
                session_id: str = "default",
                request_id: str = "req_0",
                route: str = "inference",
                timestamp: Optional[float] = None) -> DefenseResult:
        """
        Full 4-layer defense pipeline:
        1. Layer 4 (MTD): Select model config
        2. Layer 3 (InfoSec): Input sanitization check
        3. Layer 2 (Antifragile): Attack detection (immune memory + pattern analysis)
        4. Layer 1 (Formal): Output validation (constrained decoder + schema + invariants)
        5. Layer 3 (InfoSec): Output sanitization (confidence masking, DP noise)
        """
        signals: list[InterLayerSignal] = []
        pattern_hash = self.pattern_learner.hash_pattern(input_text)
        current_strength = self.defense_strength

        # --- Layer 4: MTD pre-processing ---
        mtd_config = self.mtd.get_config(
            session_id, request_id, route, timestamp,
        )

        # Signal: Layer 4 → Layer 2 ("Neues Modell aktiv")
        signals.append(InterLayerSignal(
            source="layer4", target="layer2",
            signal_type="model_selected",
            detail=f"Model: {mtd_config.model.name}",
        ))

        # --- Layer 3: Input sanitization ---
        probing_error = self.infosec.sanitize_input(input_text)
        if probing_error is not None:
            # Signal: Layer 3 → Layer 2 ("Verdaechtiges Probing erkannt")
            signals.append(InterLayerSignal(
                source="layer3", target="layer2",
                signal_type="probing_detected",
                detail=probing_error.message,
            ))
            # Teach pattern learner about this probing attempt
            features = self.pattern_learner.extract_features(input_text)
            self.pattern_learner.learn(features, is_attack=True)
            self.attack_memory.record(
                pattern_hash, "probing", "blocked", confidence=0.85,
            )

            # Signal: Layer 3 → Layer 4 ("Information Leakage steigt")
            signals.append(InterLayerSignal(
                source="layer3", target="layer4",
                signal_type="leakage_rising",
                detail="Probing attempt detected, consider faster rotation",
            ))

            # Response strategy selection
            strategy = self.strategy_selector.select(
                confidence=0.85, severity="medium",
                attack_type="probing", session_id=session_id,
                pattern_hash=pattern_hash,
            )
            fake_resp = None
            if strategy.response_type == ResponseType.DECEIVE:
                fake_resp = self.honeypot.generate("probing", input_text)
            if strategy.response_type == ResponseType.TERMINATE:
                self.strategy_selector.ban(
                    pattern_hash, strategy.ban_duration_seconds,
                )

            # TOLERATE: allow through despite detection
            if strategy.response_type == ResponseType.TOLERATE:
                signals.append(InterLayerSignal(
                    source="strategy", target="layer2",
                    signal_type="tolerate_warning",
                    detail=f"Low-confidence detection tolerated: {strategy.reason}",
                ))
                # Continue to Layer 2 instead of blocking
                # (fall through below instead of returning)
            else:
                return DefenseResult(
                    allowed=False,
                    blocked_by="layer3_infosec",
                    detail="Input sanitization: probing detected",
                    defense_strength=current_strength,
                    mtd_config=mtd_config,
                    signals=signals,
                    response_strategy=strategy.response_type,
                    fake_response=fake_resp,
                    session_banned=(strategy.response_type == ResponseType.TERMINATE),
                )

        # --- Layer 2, Step 1: Fast-path (immune memory) ---
        fast_result = self.immune_memory.fast_check(pattern_hash)
        if fast_result is True:
            self.attack_memory.record(
                pattern_hash, "known_attack", "blocked", confidence=0.95,
            )
            # Signal: Layer 2 → Layer 4 ("Known attacker")
            signals.append(InterLayerSignal(
                source="layer2", target="layer4",
                signal_type="known_attacker",
                detail=f"Known attack pattern: {pattern_hash[:12]}",
            ))
            # Response strategy: known attack = high confidence
            strategy = self.strategy_selector.select(
                confidence=0.95, severity="high",
                attack_type="known_attack", session_id=session_id,
                pattern_hash=pattern_hash,
            )
            if strategy.response_type == ResponseType.TERMINATE:
                self.strategy_selector.ban(
                    pattern_hash, strategy.ban_duration_seconds,
                )
            return DefenseResult(
                allowed=False,
                blocked_by="layer2_immune_memory",
                detail="Known attack pattern — immediate block",
                defense_strength=current_strength,
                fast_path=True,
                mtd_config=mtd_config,
                signals=signals,
                response_strategy=strategy.response_type,
                session_banned=(strategy.response_type == ResponseType.TERMINATE),
            )

        # --- Layer 2, Step 2: Feature analysis ---
        features = self.pattern_learner.extract_features(input_text)
        anomaly = self.pattern_learner.anomaly_score(features, text=input_text)

        # Adjust threshold based on false positive tracking
        effective_threshold = self.calibrator.adjusted_threshold(
            self.blocking_threshold,
            self.attack_memory.count_false_positives(),
            self.attack_memory.count_total(),
        )

        if anomaly >= effective_threshold:
            self.attack_memory.record(
                pattern_hash, "anomaly", "blocked", confidence=anomaly,
            )
            # Teach the learner
            self.pattern_learner.learn(features, is_attack=True)

            # Cross-layer redundancy: check if L1 would also catch the output
            redundancy = 1  # L2 caught it
            l1_violations = self.formal_verifier.monitor.check(output_text)
            if l1_violations:
                redundancy += 1
                signals.append(InterLayerSignal(
                    source="layer2", target="layer1",
                    signal_type="redundancy_check",
                    detail=f"L1 would also block: {len(l1_violations)} violations",
                ))

            # Response strategy based on anomaly confidence
            strategy = self.strategy_selector.select(
                confidence=anomaly, severity="medium",
                attack_type="anomaly", session_id=session_id,
                pattern_hash=pattern_hash,
            )
            fake_resp = None
            sandboxed = False
            if strategy.response_type == ResponseType.DECEIVE:
                fake_resp = self.honeypot.generate("anomaly", input_text)
            elif strategy.response_type == ResponseType.TOLERATE:
                # Allow through despite anomaly — avoid false positive
                signals.append(InterLayerSignal(
                    source="strategy", target="layer2",
                    signal_type="tolerate_warning",
                    detail=f"Anomaly tolerated (low confidence): {strategy.reason}",
                ))
                # Fall through to Layer 1 output validation
            elif strategy.response_type == ResponseType.SANDBOX:
                sandboxed = True
            elif strategy.response_type == ResponseType.TERMINATE:
                self.strategy_selector.ban(
                    pattern_hash, strategy.ban_duration_seconds,
                )

            if strategy.response_type != ResponseType.TOLERATE:
                return DefenseResult(
                    allowed=False,
                    blocked_by="layer2_pattern_analysis",
                    detail=f"Anomaly score {anomaly:.2f} >= threshold {effective_threshold:.2f}",
                    anomaly_score=anomaly,
                    defense_strength=self.defense_strength,
                    mtd_config=mtd_config,
                    signals=signals,
                    redundancy_score=redundancy,
                    response_strategy=strategy.response_type,
                    fake_response=fake_resp,
                    sandboxed=sandboxed,
                    session_banned=(strategy.response_type == ResponseType.TERMINATE),
                )

        # --- Layer 1: Output validation ---
        response, violations = self.formal_verifier.verify(
            output_text, intent, risk_level,
        )

        if violations:
            # Feedback loop: Layer 1 → Layer 2 ("Schema-Violation blockiert")
            self.attack_memory.record(
                pattern_hash, "output_violation", "blocked", confidence=0.8,
            )
            # Teach the learner about this attack
            self.pattern_learner.learn(features, is_attack=True)

            signals.append(InterLayerSignal(
                source="layer1", target="layer2",
                signal_type="schema_violation",
                detail=f"Violations: {[str(v) for v in violations]}",
            ))

            # Cross-layer redundancy: L1 caught it; check if L2 anomaly was also high
            redundancy = 1  # L1 caught it
            if anomaly >= effective_threshold:
                redundancy += 1

            # Check hormesis: Layer 2 → Layer 3 signal
            fp_count = self.attack_memory.count_false_positives()
            total = self.attack_memory.count_total()
            if self.calibrator.is_too_aggressive(fp_count, total):
                signals.append(InterLayerSignal(
                    source="layer2", target="layer3",
                    signal_type="fp_rate_high",
                    detail="False positive rate too high, consider relaxing epsilon",
                ))

            # Response strategy for formal violations (always high confidence)
            strategy = self.strategy_selector.select(
                confidence=0.8, severity="high",
                attack_type="output_violation", session_id=session_id,
                pattern_hash=pattern_hash,
            )
            if strategy.response_type == ResponseType.TERMINATE:
                self.strategy_selector.ban(
                    pattern_hash, strategy.ban_duration_seconds,
                )

            return DefenseResult(
                allowed=False,
                blocked_by="layer1_formal",
                detail=f"Invariant violations: {[str(v) for v in violations]}",
                anomaly_score=anomaly,
                defense_strength=self.defense_strength,
                mtd_config=mtd_config,
                signals=signals,
                redundancy_score=redundancy,
                response_strategy=strategy.response_type,
                session_banned=(strategy.response_type == ResponseType.TERMINATE),
            )

        # --- Layer 3: Output sanitization ---
        # Teach the learner about this normal input
        self.pattern_learner.learn(features, is_attack=False)

        output_data = {
            "content": output_text,
            "intent": intent,
            "risk_level": risk_level,
            "anomaly_score": anomaly,
            "confidence": 1.0 - anomaly,
        }
        sanitized = self.infosec.sanitize_output(
            output_data, numeric_keys={"anomaly_score", "confidence"},
        )

        # Check if any TOLERATE signals were emitted (allowed despite detection)
        tolerate_signals = [
            s for s in signals if s.signal_type == "tolerate_warning"
        ]
        has_tolerate = len(tolerate_signals) > 0

        # All clear
        return DefenseResult(
            allowed=True,
            response=response,
            anomaly_score=anomaly,
            defense_strength=self.defense_strength,
            mtd_config=mtd_config,
            output_sanitized=True,
            confidence_masked=sanitized.confidence_masked,
            noise_added=sanitized.noise_added,
            signals=signals,
            response_strategy=ResponseType.TOLERATE if has_tolerate else None,
        )

    def report_false_positive(self, input_text: str,
                              timestamp: Optional[float] = None) -> bool:
        """
        Mark an input as falsely blocked (for hormesis calibration).
        Returns True if accepted, False if rate limit exceeded.
        """
        if not self.calibrator.accept_fp_report(timestamp):
            return False

        pattern_hash = self.pattern_learner.hash_pattern(input_text)
        self.attack_memory.record(
            pattern_hash, "false_positive", "false_positive", confidence=0.0,
        )
        return True

    def close(self) -> None:
        self.attack_memory.close()


# ---------------------------------------------------------------------------
# CorrelatingDefense — Parallel Evaluation + Signal Correlation
# ---------------------------------------------------------------------------

@dataclass
class CorrelatingDefenseResult:
    """Result from the correlating defense pipeline."""
    allowed: bool
    correlation: Optional[CorrelationResult] = None
    response: Optional[SafeResponse] = None
    detail: str = ""
    # Underlying layer signals for transparency
    signals: list[LayerSignal] = field(default_factory=list)
    inter_layer_signals: list[InterLayerSignal] = field(default_factory=list)
    # Layer 4 info
    mtd_config: Optional[MTDConfig] = None


class CorrelatingDefense:
    """
    Enhanced defense that runs all layers in parallel and correlates signals.

    Unlike LayeredDefense which processes sequentially and stops at the first
    detection, this evaluates ALL layers for every request and combines weak
    signals into strong detections using the independent-failure model.

    This directly addresses the sub-additive CMF (2.3x) by catching attacks
    that no single layer would flag with sufficient confidence alone.
    """

    def __init__(self, db_path: str = ":memory:",
                 blocking_threshold: float = 0.5,
                 alpha: float = 0.05,
                 hormesis_cap: float = 2.0,
                 # Layer 3 config
                 dp_epsilon: float = 1.0,
                 dp_sensitivity: float = 1.0,
                 dp_seed: Optional[int] = None,
                 # Layer 4 config
                 model_configs: Optional[list[ModelConfig]] = None,
                 base_prompt: str = "You are a helpful assistant.",
                 mtd_secret: str = "mtd_secret",
                 rotation_seconds: int = 3600,
                 # Correlation config
                 correlation_threshold: float = 0.5):
        # Layer 2
        self.attack_memory = AttackMemory(db_path)
        self.pattern_learner = PatternLearner()
        self.calibrator = HormesisCalibrator(
            alpha=alpha, hormesis_cap=hormesis_cap,
        )
        self.immune_memory = ImmuneMemory(self.attack_memory)
        self.blocking_threshold = blocking_threshold

        # Layer 1
        self.formal_verifier = FormalVerifier()

        # Layer 3
        self.infosec = InfoSecLayer(
            epsilon=dp_epsilon, sensitivity=dp_sensitivity,
            seed=dp_seed,
        )

        # Layer 4
        self.mtd = MTDLayer(
            model_configs=model_configs,
            base_prompt=base_prompt,
            secret=mtd_secret,
            rotation_seconds=rotation_seconds,
        )

        # Correlation Engine
        self.correlation = CorrelationEngine(threshold=correlation_threshold)

    def _evaluate_layer1(self, output_text: str) -> LayerSignal:
        """
        Layer 1 (Formal): Run InvariantMonitor on the output.
        Confidence = number of violations mapped to [0, 1].
        """
        violations = self.formal_verifier.monitor.check(output_text)
        n = len(violations)
        # Map violation count to confidence: 0 -> 0.0, 1 -> 0.5, 2 -> 0.7, 3+ -> 0.9
        if n == 0:
            confidence = 0.0
            attack_type = "none"
            detail = "No invariant violations"
        else:
            confidence = min(0.3 + n * 0.2, 0.95)
            # Determine attack type from violation rules
            rules = {v.rule for v in violations}
            if "no_sql_injection" in rules:
                attack_type = "sql_injection"
            elif "no_script_tags" in rules or "no_event_handler_xss" in rules or "no_css_xss" in rules:
                attack_type = "xss"
            elif "no_pii_leakage" in rules:
                attack_type = "pii_extraction"
            elif "no_prompt_injection" in rules:
                attack_type = "prompt_injection"
            elif any(r.startswith("no_jailbreak") for r in rules):
                attack_type = "jailbreak"
            else:
                attack_type = "output_violation"
            detail = f"{n} violation(s): {[v.rule for v in violations]}"

        return LayerSignal(
            layer=1,
            layer_name="formal",
            confidence=confidence,
            attack_type=attack_type,
            detail=detail,
        )

    def _evaluate_layer2(self, input_text: str) -> LayerSignal:
        """
        Layer 2 (Antifragile): Run anomaly scoring on the input.
        Returns the anomaly score directly as confidence.
        """
        # Check immune memory first
        pattern_hash = self.pattern_learner.hash_pattern(input_text)
        fast_result = self.immune_memory.fast_check(pattern_hash)
        if fast_result is True:
            return LayerSignal(
                layer=2,
                layer_name="antifragile",
                confidence=0.95,
                attack_type="known_attack",
                detail=f"Known attack pattern: {pattern_hash[:12]}",
            )

        features = self.pattern_learner.extract_features(input_text)
        anomaly = self.pattern_learner.anomaly_score(features, text=input_text)

        if anomaly > 0.1:
            attack_type = "anomaly"
            detail = f"Anomaly score: {anomaly:.3f}"
        else:
            attack_type = "none"
            detail = f"Normal input (anomaly: {anomaly:.3f})"

        return LayerSignal(
            layer=2,
            layer_name="antifragile",
            confidence=anomaly,
            attack_type=attack_type,
            detail=detail,
        )

    def _evaluate_layer3(self, input_text: str) -> LayerSignal:
        """
        Layer 3 (InfoSec): Check for probing / information extraction attempts.
        Returns a confidence score based on probing indicator matches.
        """
        probing_indicators = [
            "what model are you",
            "system prompt",
            "your instructions",
            "repeat everything above",
            "ignore previous",
            "reveal your",
        ]
        text_lower = input_text.lower()
        hits = sum(1 for ind in probing_indicators if ind in text_lower)

        if hits == 0:
            return LayerSignal(
                layer=3,
                layer_name="infosec",
                confidence=0.0,
                attack_type="none",
                detail="No probing indicators",
            )

        # Map hits to confidence: 1 hit = 0.4, 2 = 0.6, 3+ = 0.85
        confidence = min(0.2 + hits * 0.2, 0.85)
        return LayerSignal(
            layer=3,
            layer_name="infosec",
            confidence=confidence,
            attack_type="probing",
            detail=f"{hits} probing indicator(s) matched",
        )

    def _evaluate_layer4(self, session_id: str,
                         timestamp: Optional[float] = None) -> LayerSignal:
        """
        Layer 4 (MTD): Evaluate endpoint/session fingerprinting resistance.

        In a real deployment, this would check if the client is probing
        multiple endpoints or sessions to fingerprint the rotation pattern.
        For this POC, we check if the session has been seen with suspiciously
        rapid request patterns (via attack memory).
        """
        # Check if this session has prior blocked attacks (indicates targeting)
        pattern_hash = f"session:{session_id}"
        blocked = self.attack_memory.count_blocked(pattern_hash)

        if blocked == 0:
            return LayerSignal(
                layer=4,
                layer_name="mtd",
                confidence=0.0,
                attack_type="none",
                detail="No fingerprinting indicators",
            )

        confidence = min(0.2 + blocked * 0.15, 0.8)
        return LayerSignal(
            layer=4,
            layer_name="mtd",
            confidence=confidence,
            attack_type="fingerprint",
            detail=f"Session {session_id} has {blocked} prior blocks",
        )

    def process(self, input_text: str, output_text: str,
                intent: str = "answer",
                risk_level: str = "none",
                session_id: str = "default",
                request_id: str = "req_0",
                route: str = "inference",
                timestamp: Optional[float] = None) -> CorrelatingDefenseResult:
        """
        Parallel 4-layer evaluation + correlation pipeline:
        1. Collect signals from ALL layers (never stop at first detection)
        2. Correlate signals using independent-failure model
        3. Act based on combined confidence
        """
        inter_signals: list[InterLayerSignal] = []

        # --- Layer 4: MTD config (still needed for response context) ---
        mtd_config = self.mtd.get_config(
            session_id, request_id, route, timestamp,
        )

        # --- Parallel evaluation of all 4 layers ---
        l1_signal = self._evaluate_layer1(output_text)
        l2_signal = self._evaluate_layer2(input_text)
        l3_signal = self._evaluate_layer3(input_text)
        l4_signal = self._evaluate_layer4(session_id, timestamp)

        signals = [l1_signal, l2_signal, l3_signal, l4_signal]

        # --- Correlate ---
        result = self.correlation.correlate(signals)

        # --- Record to attack memory if blocked ---
        pattern_hash = self.pattern_learner.hash_pattern(input_text)
        features = self.pattern_learner.extract_features(input_text)

        if result.combined_confidence >= self.correlation.threshold:
            # Attack detected via correlation
            self.attack_memory.record(
                pattern_hash, "correlated_attack", "blocked",
                confidence=result.combined_confidence,
            )
            self.pattern_learner.learn(features, is_attack=True)

            # Inter-layer signals for feedback
            for s in signals:
                if s.confidence > CorrelationEngine.CONTRIBUTION_THRESHOLD:
                    inter_signals.append(InterLayerSignal(
                        source=f"layer{s.layer}",
                        target="correlation_engine",
                        signal_type=f"{s.layer_name}_detection",
                        detail=s.detail,
                    ))

            return CorrelatingDefenseResult(
                allowed=False,
                correlation=result,
                detail=(
                    f"Correlated block: combined={result.combined_confidence:.3f} "
                    f"(boost=+{result.correlation_boost:.3f}), "
                    f"action={result.recommended_action}, "
                    f"layers={result.contributing_layers}"
                ),
                signals=signals,
                inter_layer_signals=inter_signals,
                mtd_config=mtd_config,
            )
        else:
            # Allowed — teach the learner about normal input
            self.pattern_learner.learn(features, is_attack=False)

            # Try to build a formal response for clean outputs
            response = None
            if l1_signal.confidence == 0.0:
                try:
                    response, _ = self.formal_verifier.verify(
                        output_text, intent, risk_level,
                    )
                except Exception:
                    pass

            return CorrelatingDefenseResult(
                allowed=True,
                correlation=result,
                response=response,
                detail=(
                    f"Allowed: combined={result.combined_confidence:.3f}, "
                    f"action={result.recommended_action}"
                ),
                signals=signals,
                inter_layer_signals=inter_signals,
                mtd_config=mtd_config,
            )

    def close(self) -> None:
        self.attack_memory.close()
