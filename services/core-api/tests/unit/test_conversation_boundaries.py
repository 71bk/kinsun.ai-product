"""Focused regressions for the conversation application boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.conversation import ConversationStartCommand, LanguageRoute
from app.schemas.conversation import LanguageRoute as SchemaLanguageRoute


def test_conversation_start_command_is_domain_owned_and_immutable() -> None:
    assert SchemaLanguageRoute is LanguageRoute
    command = ConversationStartCommand(
        language_route=LanguageRoute.ZH_TW,
        input_mode="text",
    )

    with pytest.raises(FrozenInstanceError):
        setattr(command, "input_mode", "voice")


@pytest.mark.parametrize(
    ("language_route", "input_mode"),
    [
        ("ZH_TW", "text"),
        (LanguageRoute.ZH_TW, "audio"),
    ],
)
def test_conversation_start_command_rejects_invalid_domain_values(
    language_route: object,
    input_mode: object,
) -> None:
    with pytest.raises(ValueError):
        ConversationStartCommand(
            language_route=language_route,  # type: ignore[arg-type]
            input_mode=input_mode,  # type: ignore[arg-type]
        )
