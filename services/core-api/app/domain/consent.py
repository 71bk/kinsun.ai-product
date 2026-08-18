"""Domain vocabulary for purpose-based consent."""

from __future__ import annotations

from enum import Enum


class ConsentPurpose(str, Enum):
    """Supported purposes for granting and enforcing consent."""

    BASIC_VOICE = "BASIC_VOICE"
    TRANSCRIPT_STORAGE = "TRANSCRIPT_STORAGE"
    CARE_EVENT_EXTRACTION = "CARE_EVENT_EXTRACTION"
    LONG_TERM_MEMORY = "LONG_TERM_MEMORY"
    COMPANION_SIGNAL_ANALYSIS = "COMPANION_SIGNAL_ANALYSIS"
    PROACTIVE_COMPANION = "PROACTIVE_COMPANION"
    FAMILY_SHARING = "FAMILY_SHARING"
