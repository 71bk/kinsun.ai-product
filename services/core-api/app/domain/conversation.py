"""Domain vocabulary for starting a conversation session."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

_CONVERSATION_INPUT_MODES = frozenset({"text", "voice", "voice_with_text_fallback"})


class LanguageRoute(str, Enum):
    """Supported language routes for a conversation."""

    ZH_TW = "ZH_TW"
    NAN_TW = "NAN_TW"
    HAK_TW = "HAK_TW"
    EN_US = "EN_US"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ConversationStartCommand:
    """Use-case input required to start a conversation session."""

    language_route: LanguageRoute
    input_mode: Literal["text", "voice", "voice_with_text_fallback"]

    def __post_init__(self) -> None:
        if not isinstance(self.language_route, LanguageRoute):
            raise ValueError("language_route must be a supported LanguageRoute")
        if self.input_mode not in _CONVERSATION_INPUT_MODES:
            raise ValueError("input_mode must be a supported conversation input mode")
