"""Strict request boundaries for accountless Elder creation and tablet handoff."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.assisted_elder import (
    CareProfileEntryInput,
    CreateAccountlessElderRequest,
    ExchangeAssistedSessionRequest,
)


def test_accountless_elder_request_does_not_accept_login_credentials() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CreateAccountlessElderRequest.model_validate(
            {
                "display_name": "測試長者",
                "preferred_language": "ZH_TW",
                "primary_care_setting": "DAYCARE",
                "care_unit_id": str(uuid4()),
                "email": "elder@example.invalid",
            }
        )


def test_care_profile_entry_normalizes_whitespace_without_changing_category() -> None:
    entry = CareProfileEntryInput(
        category="CARE_PRECAUTION",
        content="  轉位時需要兩人協助  ",
    )

    assert entry.content == "轉位時需要兩人協助"
    assert entry.category == "CARE_PRECAUTION"


def test_pairing_exchange_accepts_only_pairing_credential_shape() -> None:
    ExchangeAssistedSessionRequest(pairing_token="ep1_" + "a" * 43)

    with pytest.raises(ValidationError):
        ExchangeAssistedSessionRequest(pairing_token="es1_" + "a" * 43)
