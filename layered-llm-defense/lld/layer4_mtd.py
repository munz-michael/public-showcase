"""
Layer 4 — Moving Target Defense (Unpredictable Surface)

Makes the system impossible to model from the outside.
Components:
  - ModelRotator (HMAC-based model selection per session)
  - PromptVariator (semantically equivalent prompt variants)
  - EndpointRotator (HMAC-based rotating API paths)
  - MTDLayer (chains all three)
"""

import hashlib
import hmac
import math
import time
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# ModelRotator — Deterministic per session, unpredictable externally
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    """Configuration for a single model variant."""
    name: str
    system_prompt_variant: int = 0
    temperature: float = 0.7

    def __repr__(self) -> str:
        return (
            f"ModelConfig(name={self.name!r}, "
            f"variant={self.system_prompt_variant}, "
            f"temp={self.temperature})"
        )


class ModelRotator:
    """
    Selects a model config per session using HMAC(secret, session_id + time_bucket).
    Deterministic for the same session within a time bucket, but unpredictable
    to external observers who do not know the secret.
    """

    def __init__(self, configs: list[ModelConfig],
                 secret: str = "default_secret",
                 bucket_seconds: int = 3600):
        if not configs:
            raise ValueError("At least one model config required")
        self.configs = configs
        self.secret = secret.encode("utf-8")
        self.bucket_seconds = bucket_seconds

    def _time_bucket(self, timestamp: Optional[float] = None) -> int:
        """Current time bucket index."""
        ts = timestamp if timestamp is not None else time.time()
        return int(ts) // self.bucket_seconds

    def select(self, session_id: str,
               timestamp: Optional[float] = None) -> ModelConfig:
        """
        Select a model config for this session.
        HMAC(secret, session_id + time_bucket) determines the selection.
        """
        bucket = self._time_bucket(timestamp)
        message = f"{session_id}:{bucket}".encode("utf-8")
        digest = hmac.new(self.secret, message, hashlib.sha256).digest()
        index = int.from_bytes(digest[:4], "big") % len(self.configs)
        return self.configs[index]

    def select_index(self, session_id: str,
                     timestamp: Optional[float] = None) -> int:
        """Return the index of the selected config (for testing/logging)."""
        bucket = self._time_bucket(timestamp)
        message = f"{session_id}:{bucket}".encode("utf-8")
        digest = hmac.new(self.secret, message, hashlib.sha256).digest()
        return int.from_bytes(digest[:4], "big") % len(self.configs)


# ---------------------------------------------------------------------------
# PromptVariator — Semantically equivalent prompt variants
# ---------------------------------------------------------------------------

class PromptVariator:
    """
    Maintains a set of semantically equivalent system prompt variants.
    Selects one per request based on HMAC of request context.

    Variants are stored (not generated on-the-fly) to ensure consistency
    and allow review.
    """

    def __init__(self, base_prompt: str, variants: Optional[list[str]] = None,
                 secret: str = "prompt_secret"):
        self.base_prompt = base_prompt
        self.secret = secret.encode("utf-8")

        if variants:
            self.variants = variants
        else:
            # Generate default variants by restructuring the base prompt
            self.variants = self._generate_default_variants(base_prompt)

    def select(self, request_id: str) -> str:
        """Select a prompt variant for this request."""
        digest = hmac.new(
            self.secret, request_id.encode("utf-8"), hashlib.sha256
        ).digest()
        index = int.from_bytes(digest[:4], "big") % len(self.variants)
        return self.variants[index]

    def select_index(self, request_id: str) -> int:
        """Return the index of the selected variant."""
        digest = hmac.new(
            self.secret, request_id.encode("utf-8"), hashlib.sha256
        ).digest()
        return int.from_bytes(digest[:4], "big") % len(self.variants)

    @staticmethod
    def _generate_default_variants(base: str) -> list[str]:
        """
        Generate 4 semantically equivalent variants of the base prompt.
        These are simple reformulations; in production they would be
        human-reviewed for semantic equivalence.
        """
        return [
            base,
            f"Instructions: {base}",
            f"Your role: {base} Follow these guidelines strictly.",
            f"SYSTEM: {base} Respond according to the above.",
        ]

    @property
    def variant_count(self) -> int:
        return len(self.variants)


# ---------------------------------------------------------------------------
# EndpointRotator — HMAC-based rotating API paths
# ---------------------------------------------------------------------------

class EndpointRotator:
    """
    Generates HMAC-based API paths that change every rotation_seconds.
    Valid paths are deterministic for the current time bucket but
    unpredictable without knowledge of the secret.

    Format: /api/{route}/{hmac_token}
    """

    def __init__(self, secret: str = "endpoint_secret",
                 rotation_seconds: int = 3600):
        self.secret = secret.encode("utf-8")
        self.rotation_seconds = rotation_seconds

    def _time_bucket(self, timestamp: Optional[float] = None) -> int:
        ts = timestamp if timestamp is not None else time.time()
        return int(ts) // self.rotation_seconds

    def get_current_endpoint(self, route: str,
                             timestamp: Optional[float] = None) -> str:
        """
        Get the currently valid endpoint path for a route.
        Returns: /api/{route}/{hmac_token}
        """
        bucket = self._time_bucket(timestamp)
        message = f"{route}:{bucket}".encode("utf-8")
        token = hmac.new(
            self.secret, message, hashlib.sha256
        ).hexdigest()[:16]
        return f"/api/{route}/{token}"

    def validate_endpoint(self, path: str, route: str,
                          timestamp: Optional[float] = None) -> bool:
        """
        Check if a given path is currently valid for the specified route.
        Also accepts the previous time bucket to handle boundary transitions.
        """
        current = self.get_current_endpoint(route, timestamp)
        if path == current:
            return True

        # Accept previous bucket to handle clock skew
        ts = timestamp if timestamp is not None else time.time()
        prev_bucket_ts = ts - self.rotation_seconds
        previous = self.get_current_endpoint(route, prev_bucket_ts)
        return path == previous

    def get_token(self, route: str,
                  timestamp: Optional[float] = None) -> str:
        """Extract just the HMAC token for a route at current time."""
        bucket = self._time_bucket(timestamp)
        message = f"{route}:{bucket}".encode("utf-8")
        return hmac.new(
            self.secret, message, hashlib.sha256
        ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# MTDLayer — Chains ModelRotator + PromptVariator + EndpointRotator
# ---------------------------------------------------------------------------

@dataclass
class MTDConfig:
    """Current MTD configuration snapshot."""
    model: ModelConfig
    prompt_variant: str
    prompt_variant_index: int
    endpoint_token: str
    session_id: str
    request_id: str


class MTDLayer:
    """
    Chains all Layer 4 components:
      1. ModelRotator — select model per session
      2. PromptVariator — select prompt per request
      3. EndpointRotator — validate/generate endpoint paths

    Has a rotate() method (time-based, automatic) and get_config() for
    current snapshot.
    """

    def __init__(self, model_configs: Optional[list[ModelConfig]] = None,
                 base_prompt: str = "You are a helpful assistant.",
                 prompt_variants: Optional[list[str]] = None,
                 secret: str = "mtd_secret",
                 rotation_seconds: int = 3600):
        if model_configs is None:
            model_configs = [
                ModelConfig(name="model_a", system_prompt_variant=0, temperature=0.7),
                ModelConfig(name="model_b", system_prompt_variant=1, temperature=0.5),
                ModelConfig(name="model_c", system_prompt_variant=2, temperature=0.9),
            ]

        self.model_rotator = ModelRotator(
            model_configs, secret=secret,
            bucket_seconds=rotation_seconds,
        )
        self.prompt_variator = PromptVariator(
            base_prompt, variants=prompt_variants, secret=secret,
        )
        self.endpoint_rotator = EndpointRotator(
            secret=secret, rotation_seconds=rotation_seconds,
        )
        self._rotation_seconds = rotation_seconds

    def get_config(self, session_id: str, request_id: str,
                   route: str = "inference",
                   timestamp: Optional[float] = None) -> MTDConfig:
        """Get the current MTD configuration for a session/request."""
        model = self.model_rotator.select(session_id, timestamp)
        prompt = self.prompt_variator.select(request_id)
        prompt_idx = self.prompt_variator.select_index(request_id)
        token = self.endpoint_rotator.get_token(route, timestamp)

        return MTDConfig(
            model=model,
            prompt_variant=prompt,
            prompt_variant_index=prompt_idx,
            endpoint_token=token,
            session_id=session_id,
            request_id=request_id,
        )

    def validate_endpoint(self, path: str, route: str,
                          timestamp: Optional[float] = None) -> bool:
        """Check if an endpoint path is currently valid."""
        return self.endpoint_rotator.validate_endpoint(path, route, timestamp)

    def rotate(self) -> None:
        """
        Force a rotation. In practice, rotation is time-based and automatic
        (the HMAC changes with the time bucket). This method exists for
        explicit signaling in the inter-layer protocol.

        Could be triggered by Layer 3 signaling "information leakage rising".
        """
        # Rotation is inherent in the time-bucket mechanism.
        # This method serves as an explicit hook for inter-layer signals.
        # A production implementation could reduce rotation_seconds here.
        pass

    @property
    def rotation_seconds(self) -> int:
        return self._rotation_seconds
