"""Export versioned JSON Schemas from the implemented Core API DTOs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_API = ROOT / "services" / "core-api"
sys.path.insert(0, str(CORE_API))

from app.schemas.agent_run import (  # noqa: E402
    AgentRunCompletionResponse,
    AgentRunRegistrationResponse,
    CompleteAgentRunRequest,
    RegisterAgentRunRequest,
)
from app.schemas.assignment import (  # noqa: E402
    AssignmentCommandRequest,
    AssignmentListResponse,
    AssignmentResponse,
    CreateAssignmentRequest,
)
from app.schemas.assisted_elder import (  # noqa: E402
    AccountlessElderResponse,
    AcknowledgeFirstUseRequest,
    ActivatedAssistedSessionResponse,
    AssistedCompanionTurnRequest,
    CreateAccountlessElderRequest,
    CurrentAssistedSessionResponse,
    EndAssistedSessionResponse,
    ExchangeAssistedSessionRequest,
    FirstUseAcknowledgementResponse,
    IssueAssistedSessionRequest,
    IssuedAssistedSessionResponse,
)
from app.schemas.care_event import (  # noqa: E402
    CareEventListResponse,
    CareEventResponse,
    CareEventReviewResponse,
    CreateCareEventCandidateRequest,
    ReviewCareEventRequest,
)
from app.schemas.consent import (  # noqa: E402
    ConsentListResponse,
    ConsentResponse,
    CreateConsentRequest,
    RevokeConsentRequest,
)
from app.schemas.conversation import (  # noqa: E402
    CompanionTurnRequest,
    CompanionTurnResponse,
    ConsumeVoiceTicketRequest,
    CreateVoiceSessionRequest,
    CreateVoiceTicketRequest,
    TransitionVoiceSessionRequest,
    VoiceSessionResponse,
    VoiceTicketIssuedResponse,
)
from app.schemas.deletion import DeletionRequestResponse  # noqa: E402
from app.schemas.family_invitation import (  # noqa: E402
    CreateFamilyInvitationRequest,
    FamilyInvitationCreatedResponse,
    FamilyInvitationListResponse,
    FamilyInvitationStatusResponse,
)
from app.schemas.kinsun_email_auth import (  # noqa: E402
    CompletedKinsunEmailAuthResponse,
    CompleteKinsunEmailAuthRequest,
    PasswordLoginRequest,
    StartedKinsunEmailAuthResponse,
    StartKinsunEmailAuthRequest,
)
from app.schemas.memory import (  # noqa: E402
    ConfirmMemoryRequest,
    CreateMemoryCandidateRequest,
    MemoryDecisionRequest,
    MemoryDeletionResponse,
    MemoryListResponse,
    MemoryResponse,
    UpdateMemoryRequest,
    VoiceMemoryConfirmationRequest,
    VoiceMemoryDecisionResponse,
)
from app.schemas.report import (  # noqa: E402
    CreateFamilyReportDraftRequest,
    FamilyReportListResponse,
    FamilyReportResponse,
    PublishFamilyReportRequest,
    WithdrawFamilyReportRequest,
)
from app.schemas.summary import (  # noqa: E402
    CreateSummaryDraftRequest,
    RebuildSummaryRequest,
    ReviewSummaryRequest,
    SummaryListResponse,
    SummaryResponse,
    SummaryReviewResponse,
)
from app.schemas.tool import ToolRequest, ToolResult  # noqa: E402

EXPORTS = {
    "domain": {
        "RegisterAgentRunRequestV1": RegisterAgentRunRequest,
        "AgentRunRegistrationV1": AgentRunRegistrationResponse,
        "CompleteAgentRunRequestV1": CompleteAgentRunRequest,
        "AgentRunCompletionV1": AgentRunCompletionResponse,
        "CreateFamilyInvitationRequestV1": CreateFamilyInvitationRequest,
        "FamilyInvitationCreatedV1": FamilyInvitationCreatedResponse,
        "FamilyInvitationListV1": FamilyInvitationListResponse,
        "FamilyInvitationStatusV1": FamilyInvitationStatusResponse,
        "StartKinsunEmailAuthRequestV1": StartKinsunEmailAuthRequest,
        "StartedKinsunEmailAuthV1": StartedKinsunEmailAuthResponse,
        "CompleteKinsunEmailAuthRequestV1": CompleteKinsunEmailAuthRequest,
        "PasswordLoginRequestV1": PasswordLoginRequest,
        "CompletedKinsunEmailAuthV1": CompletedKinsunEmailAuthResponse,
        "CreateConsentRequestV1": CreateConsentRequest,
        "RevokeConsentRequestV1": RevokeConsentRequest,
        "ConsentV1": ConsentResponse,
        "ConsentListV1": ConsentListResponse,
        "CreateVoiceSessionRequestV1": CreateVoiceSessionRequest,
        "CreateVoiceTicketRequestV1": CreateVoiceTicketRequest,
        "ConsumeVoiceTicketRequestV1": ConsumeVoiceTicketRequest,
        "TransitionVoiceSessionRequestV1": TransitionVoiceSessionRequest,
        "VoiceSessionV1": VoiceSessionResponse,
        "VoiceTicketIssuedV1": VoiceTicketIssuedResponse,
        "CompanionTurnRequestV1": CompanionTurnRequest,
        "CompanionTurnV1": CompanionTurnResponse,
        "CreateCareEventCandidateRequestV1": CreateCareEventCandidateRequest,
        "ReviewCareEventRequestV1": ReviewCareEventRequest,
        "CareEventV1": CareEventResponse,
        "CareEventReviewV1": CareEventReviewResponse,
        "CareEventListV1": CareEventListResponse,
        "CreateMemoryCandidateRequestV1": CreateMemoryCandidateRequest,
        "ConfirmMemoryRequestV1": ConfirmMemoryRequest,
        "VoiceMemoryConfirmationRequestV1": VoiceMemoryConfirmationRequest,
        "VoiceMemoryDecisionV1": VoiceMemoryDecisionResponse,
        "MemoryDecisionRequestV1": MemoryDecisionRequest,
        "UpdateMemoryRequestV1": UpdateMemoryRequest,
        "MemoryV1": MemoryResponse,
        "MemoryListV1": MemoryListResponse,
        "MemoryDeletionV1": MemoryDeletionResponse,
        "CreateSummaryDraftRequestV1": CreateSummaryDraftRequest,
        "ReviewSummaryRequestV1": ReviewSummaryRequest,
        "RebuildSummaryRequestV1": RebuildSummaryRequest,
        "DailySummaryV1": SummaryResponse,
        "SummaryReviewV1": SummaryReviewResponse,
        "DailySummaryListV1": SummaryListResponse,
        "CreateFamilyReportDraftRequestV1": CreateFamilyReportDraftRequest,
        "PublishFamilyReportRequestV1": PublishFamilyReportRequest,
        "WithdrawFamilyReportRequestV1": WithdrawFamilyReportRequest,
        "FamilyReportV1": FamilyReportResponse,
        "FamilyReportListV1": FamilyReportListResponse,
        "CreateCareAssignmentRequestV1": CreateAssignmentRequest,
        "AssignmentCommandRequestV1": AssignmentCommandRequest,
        "CareAssignmentV1": AssignmentResponse,
        "CareAssignmentListV1": AssignmentListResponse,
        "DeletionRequestV1": DeletionRequestResponse,
        "CreateAccountlessElderRequestV1": CreateAccountlessElderRequest,
        "AccountlessElderV1": AccountlessElderResponse,
        "IssueAssistedSessionRequestV1": IssueAssistedSessionRequest,
        "IssuedAssistedSessionV1": IssuedAssistedSessionResponse,
        "ExchangeAssistedSessionRequestV1": ExchangeAssistedSessionRequest,
        "ActivatedAssistedSessionV1": ActivatedAssistedSessionResponse,
        "CurrentAssistedSessionV1": CurrentAssistedSessionResponse,
        "AcknowledgeFirstUseRequestV1": AcknowledgeFirstUseRequest,
        "FirstUseAcknowledgementV1": FirstUseAcknowledgementResponse,
        "AssistedCompanionTurnRequestV1": AssistedCompanionTurnRequest,
        "EndAssistedSessionV1": EndAssistedSessionResponse,
    },
    "tools": {
        "ToolRequestV1": ToolRequest,
        "ToolResultV1": ToolResult,
    },
}

SUCCESS_ENVELOPES = {
    "ActorProfileEnvelopeV1": "domain/ActorProfileV1.json",
    "AuthorizedElderListEnvelopeV1": "domain/AuthorizedElderListV1.json",
    "ElderSummaryEnvelopeV1": "domain/ElderSummaryV1.json",
    "ElderAccessContextEnvelopeV1": "domain/ElderAccessContextV1.json",
    "AgentRunRegistrationEnvelopeV1": "domain/AgentRunRegistrationV1.json",
    "AgentRunCompletionEnvelopeV1": "domain/AgentRunCompletionV1.json",
    "FamilyInvitationCreatedEnvelopeV1": "domain/FamilyInvitationCreatedV1.json",
    "FamilyInvitationListEnvelopeV1": "domain/FamilyInvitationListV1.json",
    "FamilyInvitationStatusEnvelopeV1": "domain/FamilyInvitationStatusV1.json",
    "StartedKinsunEmailAuthEnvelopeV1": "domain/StartedKinsunEmailAuthV1.json",
    "CompletedKinsunEmailAuthEnvelopeV1": "domain/CompletedKinsunEmailAuthV1.json",
    "ConsentEnvelopeV1": "domain/ConsentV1.json",
    "ConsentListEnvelopeV1": "domain/ConsentListV1.json",
    "VoiceSessionEnvelopeV1": "domain/VoiceSessionV1.json",
    "VoiceTicketIssuedEnvelopeV1": "domain/VoiceTicketIssuedV1.json",
    "CompanionTurnEnvelopeV1": "domain/CompanionTurnV1.json",
    "CareEventEnvelopeV1": "domain/CareEventV1.json",
    "CareEventReviewEnvelopeV1": "domain/CareEventReviewV1.json",
    "CareEventListEnvelopeV1": "domain/CareEventListV1.json",
    "MemoryEnvelopeV1": "domain/MemoryV1.json",
    "VoiceMemoryDecisionEnvelopeV1": "domain/VoiceMemoryDecisionV1.json",
    "MemoryListEnvelopeV1": "domain/MemoryListV1.json",
    "MemoryDeletionEnvelopeV1": "domain/MemoryDeletionV1.json",
    "DailySummaryEnvelopeV1": "domain/DailySummaryV1.json",
    "SummaryReviewEnvelopeV1": "domain/SummaryReviewV1.json",
    "DailySummaryListEnvelopeV1": "domain/DailySummaryListV1.json",
    "FamilyReportEnvelopeV1": "domain/FamilyReportV1.json",
    "FamilyReportListEnvelopeV1": "domain/FamilyReportListV1.json",
    "CareAssignmentEnvelopeV1": "domain/CareAssignmentV1.json",
    "CareAssignmentListEnvelopeV1": "domain/CareAssignmentListV1.json",
    "DeletionRequestEnvelopeV1": "domain/DeletionRequestV1.json",
    "AccountlessElderEnvelopeV1": "domain/AccountlessElderV1.json",
    "IssuedAssistedSessionEnvelopeV1": "domain/IssuedAssistedSessionV1.json",
    "ActivatedAssistedSessionEnvelopeV1": "domain/ActivatedAssistedSessionV1.json",
    "CurrentAssistedSessionEnvelopeV1": "domain/CurrentAssistedSessionV1.json",
    "FirstUseAcknowledgementEnvelopeV1": "domain/FirstUseAcknowledgementV1.json",
    "EndAssistedSessionEnvelopeV1": "domain/EndAssistedSessionV1.json",
    "ToolResultEnvelopeV1": "tools/ToolResultV1.json",
}

RESTRICTED_KEYS = [
    "audio",
    "audio_uri",
    "transcript",
    "transcript_text",
    "prompt",
    "full_prompt",
    "secret",
    "token",
    "asr_confidence",
]

# ToolRequestV1 contains a recursive JSON-value definition and Restricted Data
# property-name guards that Pydantic cannot faithfully round-trip. Keep that
# audited executable contract instead of silently replacing it with a weaker
# `additionalProperties: true` schema.
PRESERVE_EXISTING = {
    # These security-sensitive auth contracts are hand-audited. Pydantic's
    # generated shape loses descriptions and rewrites nullable oneOf clauses.
    "CompleteKinsunEmailAuthRequestV1",
    "CompletedKinsunEmailAuthV1",
    "PasswordLoginRequestV1",
    "StartKinsunEmailAuthRequestV1",
    "StartedKinsunEmailAuthV1",
    "ToolRequestV1",
}


def apply_semantic_constraints(title: str, schema: dict) -> None:
    """Add cross-field constraints that Pydantic validators do not export."""
    properties = schema.get("properties", {})
    if title == "CreateConsentRequestV1":
        properties["actor_confirmation"]["const"] = True
        properties["purposes"]["uniqueItems"] = True
    elif title == "CreateFamilyInvitationRequestV1":
        properties["invitee_email"]["anyOf"][0]["format"] = "email"
        properties["share_scope"]["uniqueItems"] = True
    elif title == "FamilyInvitationCreatedV1":
        properties["invitation_code"]["pattern"] = r"^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}$"
        properties["share_scope"].update(
            {"minItems": 1, "maxItems": 4, "uniqueItems": True}
        )
    elif title == "FamilyInvitationStatusV1":
        properties["share_scope"].update(
            {"minItems": 1, "maxItems": 4, "uniqueItems": True}
        )
    elif title == "CompleteKinsunEmailAuthRequestV1":
        properties["verification_code"]["pattern"] = r"^[0-9]{6}$"
        properties["password"].update(
            {"minLength": 12, "maxLength": 128, "pattern": r"^[^\u0000]+$"}
        )
    elif title == "PasswordLoginRequestV1":
        properties["password"].update(
            {"minLength": 12, "maxLength": 128, "pattern": r"^[^\u0000]+$"}
        )
    elif title == "VoiceMemoryConfirmationRequestV1":
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"confirmation_method": {"const": "WITNESSED_VOICE"}},
                    "required": ["confirmation_method"],
                },
                "then": {
                    "required": ["witness_actor_id", "witness_evidence_reference"],
                    "properties": {
                        "witness_actor_id": {"type": "string", "format": "uuid"},
                        "witness_evidence_reference": {
                            "type": "string",
                            "pattern": r"^evidence:[0-9a-fA-F-]{36}$",
                        },
                    },
                },
                "else": {
                    "properties": {
                        "witness_actor_id": {"type": "null"},
                        "witness_evidence_reference": {"type": "null"},
                    }
                },
            }
        ]
    elif title == "StartedKinsunEmailAuthV1":
        properties["challenge_token"]["pattern"] = r"^ke1_[A-Za-z0-9_-]{43}$"
        schema["required"] = ["status", "challenge_token", "expires_at"]
    elif title == "CompletedKinsunEmailAuthV1":
        properties["session_token"]["pattern"] = r"^ks1_[A-Za-z0-9_-]{43}$"
        schema["required"] = [
            "status",
            "session_token",
            "idle_expires_at",
            "absolute_expires_at",
        ]
    elif title == "FamilyInvitationListV1":
        status = schema["$defs"]["FamilyInvitationStatusResponse"]
        status["properties"]["share_scope"].update(
            {"minItems": 1, "maxItems": 4, "uniqueItems": True}
        )
    elif title == "VoiceTicketIssuedV1":
        schema.pop("$defs", None)
        properties["voice_session"] = {
            "$ref": "https://kinsun.ai/contracts/schemas/domain/VoiceSessionV1.json"
        }
    elif title == "RevokeConsentRequestV1":
        properties["revoke_scope"]["items"]["enum"] = [
            "CONVERSATION_SESSION",
            "TRANSCRIPT",
            "AUDIO_OBJECT",
            "CARE_EVENT",
            "DAILY_SUMMARY",
            "MEMORY",
            "FAMILY_REPORT",
            "NOTIFICATION",
            "SECURE_LINK",
            "COMPANION_SIGNAL",
            "PROACTIVE_TRIGGER",
            "GRAPH",
            "SEARCH_INDEX",
            "CACHE",
        ]
    elif title == "CreateCareEventCandidateRequestV1":
        properties["structured_payload"]["propertyNames"] = {
            "not": {"enum": RESTRICTED_KEYS}
        }
        schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {
                        "source_type": {"const": "CONVERSATION_SESSION"},
                    },
                    "required": ["source_type"],
                },
                "then": {
                    "required": ["source_id"],
                    "properties": {
                        "source_id": {
                            "type": "string",
                            "format": "uuid",
                        }
                    },
                },
            }
        )
    elif title == "ReviewCareEventRequestV1":
        corrected = properties["corrected_payload"]
        object_schema = corrected["anyOf"][0]
        object_schema["propertyNames"] = {"not": {"enum": RESTRICTED_KEYS}}
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"decision": {"const": "CORRECT"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "required": ["corrected_payload"],
                        "properties": {
                            "corrected_payload": {"type": "object"},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {
                            "decision": {
                                "enum": ["VERIFY", "REJECT", "EXCLUDE"],
                            }
                        },
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {
                            "corrected_payload": {"type": "null"},
                        }
                    },
                },
            ]
        )
    elif title == "CreateSummaryDraftRequestV1":
        schema.setdefault("anyOf", []).extend(
            [
                {
                    "properties": {
                        "items": {"minItems": 1},
                    },
                    "required": ["items"],
                },
                {
                    "properties": {
                        "missing_fields": {"minItems": 1},
                    },
                    "required": ["missing_fields"],
                },
            ]
        )
    elif title == "CreateFamilyReportDraftRequestV1":
        schema.setdefault("anyOf", []).extend(
            [
                {
                    "properties": {
                        "source_summary_ids": {"minItems": 1},
                    },
                    "required": ["source_summary_ids"],
                },
                {
                    "properties": {
                        "source_event_ids": {"minItems": 1},
                    },
                    "required": ["source_event_ids"],
                },
            ]
        )
    elif title == "DeletionRequestV1":
        item = schema["$defs"]["DeletionJobItemResponse"]
        item["properties"]["attempt_count"]["minimum"] = 0
        failure_code = item["properties"]["failure_code"]["anyOf"][0]
        failure_code["minLength"] = 1
        failure_code["maxLength"] = 120
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"status": {"const": "COMPLETED"}},
                    "required": ["status"],
                },
                "then": {
                    "properties": {
                        "completed_at": {"format": "date-time", "type": "string"},
                        "items": {
                            "items": {
                                "properties": {
                                    "status": {"enum": ["COMPLETED", "SKIPPED"]}
                                }
                            }
                        },
                    }
                },
            },
            {
                "if": {
                    "properties": {"status": {"const": "PARTIAL_FAILED"}},
                    "required": ["status"],
                },
                "then": {
                    "properties": {
                        "completed_at": {"type": "null"},
                        "items": {
                            "contains": {
                                "properties": {"status": {"const": "FAILED"}},
                                "required": ["status"],
                            },
                            "minContains": 1,
                        },
                    }
                },
            },
        ]
    elif title in {"FirstUseAcknowledgementV1", "CurrentAssistedSessionV1"}:
        acknowledgement = (
            schema["$defs"]["FirstUseAcknowledgementResponse"]
            if title == "CurrentAssistedSessionV1"
            else schema
        )
        evidence_fields = [
            "consent_version",
            "acknowledged_at",
            "confirmation_method",
        ]
        acknowledgement["allOf"] = [
            {
                "if": {
                    "properties": {"status": {"const": "ACKNOWLEDGED"}},
                    "required": ["status"],
                },
                "then": {
                    "required": evidence_fields,
                    "properties": {
                        "consent_version": {"type": "integer", "minimum": 1},
                        "acknowledged_at": {"type": "string", "format": "date-time"},
                        "confirmation_method": {
                            "enum": [
                                "ACTOR_CONFIRMATION",
                                "ASSISTED_TABLET_ACKNOWLEDGEMENT",
                            ]
                        },
                    },
                },
                "else": {
                    "required": evidence_fields,
                    "properties": {
                        "consent_version": {"type": "null"},
                        "acknowledged_at": {"type": "null"},
                        "confirmation_method": {"type": "null"},
                    },
                },
            }
        ]


def main() -> None:
    base = ROOT / "contracts" / "schemas"
    for folder, exports in EXPORTS.items():
        destination = base / folder
        destination.mkdir(parents=True, exist_ok=True)
        for title, model in exports.items():
            path = destination / f"{title}.json"
            if title in PRESERVE_EXISTING and path.is_file():
                print(f"preserved {path.relative_to(ROOT)}")
                continue
            schema = model.model_json_schema(mode="validation")
            schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
            schema["$id"] = f"https://kinsun.ai/contracts/schemas/{folder}/{title}.json"
            schema["title"] = title
            apply_semantic_constraints(title, schema)
            path.write_text(
                json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            print(path.relative_to(ROOT))
    common = base / "common"
    for title, data_schema in SUCCESS_ENVELOPES.items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://kinsun.ai/contracts/schemas/common/{title}.json",
            "title": title,
            "type": "object",
            "additionalProperties": False,
            "required": ["data", "meta"],
            "properties": {
                "data": {
                    "$ref": f"https://kinsun.ai/contracts/schemas/{data_schema}",
                },
                "meta": {
                    "$ref": (
                        "https://kinsun.ai/contracts/schemas/common/ResponseMetaV1.json"
                    ),
                },
            },
        }
        path = common / f"{title}.json"
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
