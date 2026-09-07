"""Compatibility re-exports for canonical duplicate fingerprinting."""

import subprocess

from dj_digger.core.duplicates.fingerprint import (
    FINGERPRINT_VERSION,
    ChromaprintExtractor,
    Fingerprint,
    FingerprintExtractionError,
)

__all__ = [
    "FINGERPRINT_VERSION",
    "ChromaprintExtractor",
    "Fingerprint",
    "FingerprintExtractionError",
    "subprocess",
]
