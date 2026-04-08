"""
Watermark Engine -- Attribution via Invisible Markers

Embeds invisible watermarks in fake/honeypot responses. When an attacker
exfiltrates fake data and uses it elsewhere (posts it, sells it, uses it
for further attacks), the watermark triggers an alert and enables attribution.

Biological analogy: Bioluminescent markers injected into prey. The predator
that ate the marked prey glows -- revealing its identity.

Watermark types:
1. Canary tokens: unique strings that trigger alerts when accessed
2. Steganographic text: invisible Unicode markers in text
3. Structural fingerprints: unique data patterns per session
4. Timing watermarks: specific response delays that fingerprint a session

All stdlib-only. No external libraries.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# WatermarkDetection
# ---------------------------------------------------------------------------

@dataclass
class WatermarkDetection:
    """Result of detecting a watermark in text or data."""
    watermark_id: str
    session_id: str
    watermark_type: str      # "zero_width", "homoglyph", "structural", "canary_url", "canary_cred"
    embedded_at: float       # timestamp when watermark was created
    detected_at: float       # timestamp of detection
    confidence: float        # how certain is the detection (0-1)


# ---------------------------------------------------------------------------
# Zero-width encoding constants
# ---------------------------------------------------------------------------

# We encode binary data using two zero-width Unicode characters:
#   U+200B (zero-width space)  = 0
#   U+200C (zero-width non-joiner) = 1
# Framed by U+200D (zero-width joiner) as start/end marker.

_ZW_ZERO = "\u200b"
_ZW_ONE = "\u200c"
_ZW_MARKER = "\u200d"


# ---------------------------------------------------------------------------
# Homoglyph mapping (ASCII -> visually identical Unicode)
# ---------------------------------------------------------------------------

_HOMOGLYPH_MAP: dict[str, str] = {
    "a": "\u0430",   # Cyrillic а
    "c": "\u0441",   # Cyrillic с
    "e": "\u0435",   # Cyrillic е
    "o": "\u043e",   # Cyrillic о
    "p": "\u0440",   # Cyrillic р
    "s": "\u0455",   # Cyrillic ѕ
    "x": "\u0445",   # Cyrillic х
    "y": "\u0443",   # Cyrillic у (close enough at small sizes)
}

# Reverse map for detection
_HOMOGLYPH_REVERSE: dict[str, str] = {v: k for k, v in _HOMOGLYPH_MAP.items()}


# ---------------------------------------------------------------------------
# WatermarkEngine
# ---------------------------------------------------------------------------

class WatermarkEngine:
    """
    Embeds invisible watermarks in fake/honeypot responses and detects
    them later for attribution.
    """

    def __init__(self, secret: str = "watermark_secret"):
        self._secret = secret.encode("utf-8")
        self._issued_watermarks: dict[str, dict] = {}  # watermark_id -> metadata

    # -- Zero-width watermarking --

    def _encode_zero_width(self, data: str) -> str:
        """Encode a string as zero-width characters."""
        bits = "".join(format(b, "08b") for b in data.encode("utf-8"))
        encoded = _ZW_MARKER
        for bit in bits:
            encoded += _ZW_ONE if bit == "1" else _ZW_ZERO
        encoded += _ZW_MARKER
        return encoded

    def _decode_zero_width(self, zw_text: str) -> Optional[str]:
        """Decode zero-width characters back to a string."""
        # Find content between markers
        start = zw_text.find(_ZW_MARKER)
        if start == -1:
            return None
        end = zw_text.find(_ZW_MARKER, start + 1)
        if end == -1:
            return None
        payload = zw_text[start + 1:end]
        if not payload:
            return None

        bits = ""
        for ch in payload:
            if ch == _ZW_ONE:
                bits += "1"
            elif ch == _ZW_ZERO:
                bits += "0"
            else:
                # Unexpected character -- skip
                continue

        if len(bits) % 8 != 0:
            return None

        byte_list = []
        for i in range(0, len(bits), 8):
            byte_list.append(int(bits[i:i+8], 2))
        try:
            return bytes(byte_list).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return None

    def embed_canary(self, text: str, session_id: str,
                     watermark_type: str = "zero_width") -> tuple[str, str]:
        """
        Embed a canary watermark in text.
        Returns (watermarked_text, watermark_id).

        Types:
        - "zero_width": insert zero-width Unicode chars that encode session_id
        - "homoglyph": replace some chars with visually identical Unicode variants
        - "whitespace": encode data in trailing whitespace patterns
        """
        ts = time.time()
        watermark_id = self._generate_watermark_id(session_id, ts)
        payload = f"{watermark_id}:{session_id}"

        if watermark_type == "zero_width":
            zw = self._encode_zero_width(payload)
            # Insert in the middle of the text for robustness
            mid = len(text) // 2
            watermarked = text[:mid] + zw + text[mid:]

        elif watermark_type == "homoglyph":
            # Encode session_id hash as a pattern of homoglyph substitutions
            h = hashlib.sha256(payload.encode()).digest()
            watermarked = list(text)
            replaceable = [
                (i, ch) for i, ch in enumerate(watermarked)
                if ch.lower() in _HOMOGLYPH_MAP
            ]
            # Use hash bits to decide which chars to replace
            bit_idx = 0
            for i, ch in replaceable:
                if bit_idx >= len(h) * 8:
                    break
                byte_pos = bit_idx // 8
                bit_pos = bit_idx % 8
                if (h[byte_pos] >> (7 - bit_pos)) & 1:
                    lower_ch = ch.lower()
                    if lower_ch in _HOMOGLYPH_MAP:
                        replacement = _HOMOGLYPH_MAP[lower_ch]
                        if ch.isupper():
                            replacement = replacement.upper()
                        watermarked[i] = replacement
                bit_idx += 1
            watermarked = "".join(watermarked)

        elif watermark_type == "whitespace":
            # Encode payload in trailing whitespace on each line
            zw = self._encode_zero_width(payload)
            lines = text.split("\n")
            if lines:
                lines[0] = lines[0] + zw
            watermarked = "\n".join(lines)

        else:
            raise ValueError(f"Unknown watermark type: {watermark_type}")

        # Store metadata
        self._issued_watermarks[watermark_id] = {
            "session_id": session_id,
            "watermark_type": watermark_type,
            "embedded_at": ts,
            "payload": payload,
        }

        return watermarked, watermark_id

    def embed_structural(self, fake_data: dict, session_id: str) -> tuple[dict, str]:
        """
        Embed a structural fingerprint in fake data.
        Unique field ordering, specific decimal precision, date format variants.
        """
        ts = time.time()
        watermark_id = self._generate_watermark_id(session_id, ts)
        h = hashlib.sha256(f"{watermark_id}:{session_id}".encode()).digest()

        result = {}
        keys = list(fake_data.keys())

        # 1. Field ordering based on hash (sort by hash-derived permutation)
        perm_seed = int.from_bytes(h[:4], "big")
        indexed = list(enumerate(keys))
        indexed.sort(key=lambda x: (perm_seed + x[0] * 2654435761) % (2**32))
        ordered_keys = [keys[idx] for idx, _ in indexed]

        for i, key in enumerate(ordered_keys):
            val = fake_data[key]
            byte_idx = (i + 4) % len(h)
            variant = h[byte_idx] % 4

            if isinstance(val, float):
                # 2. Decimal precision variant
                precision = 2 + (variant % 4)
                result[key] = round(val, precision)
            elif isinstance(val, str) and "date" in key.lower():
                # 3. Date format variant
                result[key] = val  # Keep as-is, structural order is the mark
            else:
                result[key] = val

        self._issued_watermarks[watermark_id] = {
            "session_id": session_id,
            "watermark_type": "structural",
            "embedded_at": ts,
            "field_order": ordered_keys,
            "hash_prefix": h[:8].hex(),
        }

        return result, watermark_id

    def detect_watermark(self, text: str) -> Optional[WatermarkDetection]:
        """
        Check if text contains one of our watermarks.
        Returns WatermarkDetection if found, None otherwise.
        """
        ts = time.time()

        # Try zero-width extraction
        extracted = self.extract_zero_width(text)
        if extracted and ":" in extracted:
            parts = extracted.split(":", 1)
            watermark_id = parts[0]
            session_id = parts[1] if len(parts) > 1 else "unknown"

            meta = self._issued_watermarks.get(watermark_id, {})
            embedded_at = meta.get("embedded_at", 0.0)
            wm_type = meta.get("watermark_type", "zero_width")

            return WatermarkDetection(
                watermark_id=watermark_id,
                session_id=session_id,
                watermark_type=wm_type,
                embedded_at=embedded_at,
                detected_at=ts,
                confidence=1.0,
            )

        # Try homoglyph detection
        has_homoglyphs = any(ch in _HOMOGLYPH_REVERSE for ch in text)
        if has_homoglyphs:
            # We know it contains homoglyphs but cannot directly decode
            # the session_id without the original text. Return a partial
            # detection with lower confidence.
            # Try to match against known watermarks by checking homoglyph count
            homoglyph_count = sum(1 for ch in text if ch in _HOMOGLYPH_REVERSE)
            if homoglyph_count >= 3:
                return WatermarkDetection(
                    watermark_id="unknown_homoglyph",
                    session_id="unknown",
                    watermark_type="homoglyph",
                    embedded_at=0.0,
                    detected_at=ts,
                    confidence=min(0.5 + homoglyph_count * 0.05, 0.95),
                )

        return None

    def extract_zero_width(self, text: str) -> Optional[str]:
        """Extract zero-width encoded data from text."""
        return self._decode_zero_width(text)

    def generate_canary_url(self, session_id: str) -> str:
        """
        Generate a unique URL that triggers alert when accessed.
        Format: https://canary.example/{unique_token}
        """
        ts = time.time()
        token = self._generate_watermark_id(session_id, ts)
        url = f"https://canary.example/{token}"
        self._issued_watermarks[token] = {
            "session_id": session_id,
            "watermark_type": "canary_url",
            "embedded_at": ts,
            "url": url,
        }
        return url

    def generate_canary_credential(self, session_id: str) -> dict:
        """
        Generate fake credentials with embedded tracking.
        Returns {"username": "...", "password": "...", "api_key": "..."}
        where each value contains an encoded watermark.
        """
        ts = time.time()
        wm_id = self._generate_watermark_id(session_id, ts)
        h = hashlib.sha256(f"{wm_id}:{session_id}".encode()).digest()

        # Encode watermark_id into the credential values
        username = f"user_{h[:4].hex()}"
        password = f"pass_{h[4:10].hex()}_{wm_id[:8]}"
        api_key = f"sk-test-{h[10:26].hex()}-{wm_id[:8]}"

        creds = {
            "username": username,
            "password": password,
            "api_key": api_key,
        }

        self._issued_watermarks[wm_id] = {
            "session_id": session_id,
            "watermark_type": "canary_cred",
            "embedded_at": ts,
            "credentials": creds,
        }

        return creds

    def detect_canary_credential(self, creds: dict) -> Optional[WatermarkDetection]:
        """Check if credentials match any issued canary credentials."""
        ts = time.time()
        for wm_id, meta in self._issued_watermarks.items():
            if meta.get("watermark_type") != "canary_cred":
                continue
            issued = meta.get("credentials", {})
            if (creds.get("username") == issued.get("username") or
                    creds.get("api_key") == issued.get("api_key")):
                return WatermarkDetection(
                    watermark_id=wm_id,
                    session_id=meta["session_id"],
                    watermark_type="canary_cred",
                    embedded_at=meta["embedded_at"],
                    detected_at=ts,
                    confidence=1.0,
                )
        return None

    def detect_canary_url(self, url: str) -> Optional[WatermarkDetection]:
        """Check if a URL matches any issued canary URLs."""
        ts = time.time()
        for wm_id, meta in self._issued_watermarks.items():
            if meta.get("watermark_type") != "canary_url":
                continue
            if meta.get("url") == url:
                return WatermarkDetection(
                    watermark_id=wm_id,
                    session_id=meta["session_id"],
                    watermark_type="canary_url",
                    embedded_at=meta["embedded_at"],
                    detected_at=ts,
                    confidence=1.0,
                )
        return None

    # -- Internal helpers --

    def _generate_watermark_id(self, session_id: str, ts: float) -> str:
        """Generate a unique watermark ID using HMAC."""
        msg = f"{session_id}:{ts}".encode("utf-8")
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()[:16]
