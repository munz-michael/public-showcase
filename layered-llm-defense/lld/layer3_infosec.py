"""
Layer 3 — Information-Theoretic Security (Zero-Leakage Interface)

Gives the attacker zero exploitable feedback.
Components:
  - ConfidenceMasker (bucketize confidence scores)
  - ErrorSanitizer (generic error responses, no model info leakage)
  - DPNoiseMixin (Laplace noise on numerical outputs)
  - InfoSecLayer (chains all three)
"""

import hashlib
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# ConfidenceMasker — Bucketize confidence to prevent logprob probing
# ---------------------------------------------------------------------------

class ConfidenceBucket(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ConfidenceMasker:
    """
    Replaces exact confidence/logprob values with fixed buckets.
    Prevents model probing via logprob analysis.

    Thresholds:
      [0.0, low_threshold)   -> low
      [low_threshold, high_threshold) -> medium
      [high_threshold, 1.0]  -> high
    """

    def __init__(self, low_threshold: float = 0.4, high_threshold: float = 0.75):
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold

    def mask(self, confidence: float) -> ConfidenceBucket:
        """Map exact confidence to a fixed bucket."""
        if confidence < self.low_threshold:
            return ConfidenceBucket.low
        elif confidence < self.high_threshold:
            return ConfidenceBucket.medium
        else:
            return ConfidenceBucket.high

    def mask_dict(self, data: dict) -> dict:
        """
        Recursively mask any 'confidence', 'logprob', 'probability' keys
        in a dictionary. Returns a new dict with masked values.
        """
        masked = {}
        sensitive_keys = {"confidence", "logprob", "probability", "score",
                          "logprobs", "token_logprobs"}
        for key, value in data.items():
            if key in sensitive_keys and isinstance(value, (int, float)):
                masked[key] = self.mask(value).value
            elif isinstance(value, dict):
                masked[key] = self.mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_dict(item) if isinstance(item, dict)
                    else self.mask(item).value if (
                        isinstance(item, (int, float)) and key in sensitive_keys
                    )
                    else item
                    for item in value
                ]
            else:
                masked[key] = value
        return masked


# ---------------------------------------------------------------------------
# ErrorSanitizer — Generic error messages, no internal state leakage
# ---------------------------------------------------------------------------

class ExternalErrorCategory(str, Enum):
    invalid_request = "invalid_request"
    service_error = "service_error"
    rate_limited = "rate_limited"


# Internal error types mapped to external categories
_ERROR_MAP: dict[str, ExternalErrorCategory] = {
    # Invalid request family
    "schema_validation": ExternalErrorCategory.invalid_request,
    "constrained_decoding": ExternalErrorCategory.invalid_request,
    "pii_detected": ExternalErrorCategory.invalid_request,
    "input_too_long": ExternalErrorCategory.invalid_request,
    "invalid_intent": ExternalErrorCategory.invalid_request,
    "invalid_field": ExternalErrorCategory.invalid_request,
    "validation_error": ExternalErrorCategory.invalid_request,
    # Service error family
    "model_error": ExternalErrorCategory.service_error,
    "inference_timeout": ExternalErrorCategory.service_error,
    "internal_error": ExternalErrorCategory.service_error,
    "layer_error": ExternalErrorCategory.service_error,
    "oom_error": ExternalErrorCategory.service_error,
    # Rate limiting family
    "rate_limit": ExternalErrorCategory.rate_limited,
    "quota_exceeded": ExternalErrorCategory.rate_limited,
    "concurrent_limit": ExternalErrorCategory.rate_limited,
}

# Generic messages per category (never leak specifics)
_EXTERNAL_MESSAGES: dict[ExternalErrorCategory, str] = {
    ExternalErrorCategory.invalid_request: "The request could not be processed. Please check your input.",
    ExternalErrorCategory.service_error: "The service encountered an error. Please try again later.",
    ExternalErrorCategory.rate_limited: "Too many requests. Please wait before retrying.",
}

# Strings that must never appear in external error messages
_FORBIDDEN_LEAK_PATTERNS = [
    "gpt-", "claude-", "llama-", "mistral-", "gemini-",  # model names
    "v1.", "v2.", "v3.", "v4.",  # version strings
    "torch.", "transformers.", "openai.",  # library internals
    "CUDA", "GPU", "tensor",  # hardware details
    "traceback", "stack trace", "line ",  # debug info
    "/home/", "/usr/", "/opt/", "/var/",  # file paths
]


@dataclass
class SanitizedError:
    """External-facing error with no internal details."""
    category: ExternalErrorCategory
    message: str
    request_id: str = ""


class ErrorSanitizer:
    """
    Replaces detailed internal errors with generic external categories.
    Never leaks model name, version, file paths, or internal state.
    """

    def sanitize(self, internal_error_type: str,
                 internal_detail: str = "",
                 request_id: str = "") -> SanitizedError:
        """
        Map an internal error to a safe external representation.
        The internal_detail is NEVER passed through to the external message.
        """
        category = _ERROR_MAP.get(
            internal_error_type, ExternalErrorCategory.service_error
        )
        message = _EXTERNAL_MESSAGES[category]

        # Generate a safe request ID if not provided
        if not request_id:
            request_id = hashlib.sha256(
                f"{internal_error_type}:{id(self)}".encode()
            ).hexdigest()[:12]

        return SanitizedError(
            category=category,
            message=message,
            request_id=request_id,
        )

    @staticmethod
    def contains_leak(text: str) -> bool:
        """Check if text contains any forbidden leak patterns."""
        text_lower = text.lower()
        return any(
            pattern.lower() in text_lower for pattern in _FORBIDDEN_LEAK_PATTERNS
        )


# ---------------------------------------------------------------------------
# DPNoiseMixin — Laplace noise for differential privacy
# ---------------------------------------------------------------------------

class DPNoiseMixin:
    """
    Adds calibrated Laplace noise to numerical outputs.

    Implements the differential privacy guarantee:
      P(output | D) <= e^epsilon * P(output | D')
    for all neighboring datasets D, D'.

    Sensitivity is the maximum change in the output when one record changes.
    """

    def __init__(self, epsilon: float = 1.0, sensitivity: float = 1.0,
                 seed: Optional[int] = None):
        if epsilon <= 0:
            raise ValueError("Epsilon must be positive")
        if sensitivity <= 0:
            raise ValueError("Sensitivity must be positive")
        self.epsilon = epsilon
        self.sensitivity = sensitivity
        self._rng = random.Random(seed)

    def _laplace_noise(self) -> float:
        """
        Generate Laplace noise with scale = sensitivity / epsilon.
        Uses inverse CDF: X = -b * sign(U) * ln(1 - 2|U|), U ~ Uniform(-0.5, 0.5)
        """
        scale = self.sensitivity / self.epsilon
        u = self._rng.uniform(-0.5, 0.5)
        # Avoid log(0)
        if abs(u) < 1e-15:
            return 0.0
        sign = 1.0 if u >= 0 else -1.0
        return -scale * sign * math.log(1.0 - 2.0 * abs(u))

    def add_noise(self, value: float) -> float:
        """Add Laplace noise to a single value."""
        return value + self._laplace_noise()

    def add_noise_to_dict(self, data: dict,
                          numeric_keys: Optional[set[str]] = None) -> dict:
        """
        Add Laplace noise to specified numeric fields in a dictionary.
        If numeric_keys is None, adds noise to ALL numeric values.
        """
        noised = {}
        for key, value in data.items():
            if isinstance(value, (int, float)):
                if numeric_keys is None or key in numeric_keys:
                    noised[key] = self.add_noise(float(value))
                else:
                    noised[key] = value
            elif isinstance(value, dict):
                noised[key] = self.add_noise_to_dict(value, numeric_keys)
            else:
                noised[key] = value
        return noised

    def verify_dp_bound(self, original: float, noised: float,
                        n_samples: int = 1000) -> float:
        """
        Empirical check: estimate the privacy loss for a single observation.
        Returns the empirical ratio (should be <= e^epsilon for DP guarantee).

        This is a diagnostic tool, not a proof.
        """
        scale = self.sensitivity / self.epsilon
        if scale == 0:
            return float("inf")
        # For Laplace mechanism, the exact privacy loss for a single
        # observation at distance d is e^(d * epsilon / sensitivity)
        distance = abs(original - noised)
        return math.exp(distance * self.epsilon / self.sensitivity)


# ---------------------------------------------------------------------------
# InfoSecLayer — Chains ConfidenceMasker + ErrorSanitizer + DPNoiseMixin
# ---------------------------------------------------------------------------

@dataclass
class InfoSecResult:
    """Result of Layer 3 processing."""
    data: dict = field(default_factory=dict)
    error: Optional[SanitizedError] = None
    confidence_masked: bool = False
    noise_added: bool = False
    leak_detected: bool = False


class InfoSecLayer:
    """
    Chains all Layer 3 components:
      1. ConfidenceMasker — bucketize confidence scores
      2. DPNoiseMixin — add Laplace noise to numeric outputs
      3. ErrorSanitizer — sanitize any error messages

    Used both on input (sanitization check) and output (masking + noise).
    """

    def __init__(self, epsilon: float = 1.0, sensitivity: float = 1.0,
                 low_threshold: float = 0.4, high_threshold: float = 0.75,
                 seed: Optional[int] = None):
        self.masker = ConfidenceMasker(low_threshold, high_threshold)
        self.sanitizer = ErrorSanitizer()
        self.dp_noise = DPNoiseMixin(
            epsilon=epsilon, sensitivity=sensitivity, seed=seed,
        )

    def sanitize_input(self, input_text: str) -> Optional[SanitizedError]:
        """
        Check input for suspicious probing patterns.
        Returns a SanitizedError if probing is detected, None otherwise.
        """
        # Detect attempts to extract model info via crafted prompts
        probing_indicators = [
            "what model are you",
            "system prompt",
            "your instructions",
            "repeat everything above",
            "ignore previous",
            "reveal your",
        ]
        text_lower = input_text.lower()
        for indicator in probing_indicators:
            if indicator in text_lower:
                return self.sanitizer.sanitize(
                    "invalid_request",
                    f"Probing attempt: {indicator}",
                )
        return None

    def sanitize_output(self, output_data: dict,
                        numeric_keys: Optional[set[str]] = None) -> InfoSecResult:
        """
        Full output sanitization:
          1. Mask confidence/logprob values
          2. Add DP noise to numeric fields
          3. Check for information leaks
        """
        result = InfoSecResult()

        # Step 1: Mask confidence
        masked = self.masker.mask_dict(output_data)
        result.confidence_masked = True

        # Step 2: Add DP noise to remaining numeric values
        noised = self.dp_noise.add_noise_to_dict(masked, numeric_keys)
        result.noise_added = True

        # Step 3: Check for leaks in string values
        for key, value in noised.items():
            if isinstance(value, str) and self.sanitizer.contains_leak(value):
                result.leak_detected = True
                noised[key] = "[REDACTED]"

        result.data = noised
        return result

    def sanitize_error(self, error_type: str,
                       detail: str = "") -> SanitizedError:
        """Sanitize an error message for external consumption."""
        return self.sanitizer.sanitize(error_type, detail)
