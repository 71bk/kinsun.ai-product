"""Validate the contract artifacts.

Checks three things:
1. Every JSON Schema file is itself a valid 2020-12 schema.
2. The OpenAPI document parses and its internal $refs resolve.
3. Every AsyncAPI document parses and all local/external $refs resolve.
4. Each example under contracts/examples validates (or fails to validate,
   for the invalid/ ones) against the schema it claims to describe.

The invalid/ examples MUST fail. An invalid example that passes means the
schema is too permissive, which is the failure mode worth catching.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(sys.argv[1])
SCHEMAS = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"

# example file -> schema that its "data" member must satisfy
DATA_SCHEMA_FOR = {
    "elder-summary.json": "domain/ElderSummaryV1.json",
    "elder-access-context.json": "domain/ElderAccessContextV1.json",
    "authorized-elders.json": "domain/AuthorizedElderListV1.json",
    "elder-summary-bad-care-setting.json": "domain/ElderSummaryV1.json",
    "actor-profile-legal-representative.json": "domain/ActorProfileV1.json",
    "authorized-elders-offset-pagination.json": "domain/AuthorizedElderListV1.json",
    "deletion-request.json": "domain/DeletionRequestV1.json",
    "deletion-request-completed-with-pending-item.json": "domain/DeletionRequestV1.json",
    "agent-run-request.json": "agent/AgentRunRequestV1.json",
    "agent-run-response.json": "agent/AgentRunResponseV1.json",
    "event-candidate-proposal.json": "agent/EventCandidateProposalV1.json",
    "memory-candidate-proposal.json": "agent/MemoryCandidateProposalV1.json",
    "memory-candidate-proposal-with-scope.json": (
        "agent/MemoryCandidateProposalV1.json"
    ),
    "event-candidate-proposal-with-transcript.json": (
        "agent/EventCandidateProposalV1.json"
    ),
    "agent-run-request-extra-field.json": "agent/AgentRunRequestV1.json",
    "agent-run-request-missing-required.json": "agent/AgentRunRequestV1.json",
    "agent-run-request-memory-with-status.json": "agent/AgentRunRequestV1.json",
    "agent-run-request-knowledge-with-memory.json": "agent/AgentRunRequestV1.json",
    "agent-run-registration-request.json": "domain/RegisterAgentRunRequestV1.json",
    "agent-run-registration-response.json": "domain/AgentRunRegistrationV1.json",
    "agent-run-registration-with-identity.json": "domain/RegisterAgentRunRequestV1.json",
    "agent-run-completion-request.json": "domain/CompleteAgentRunRequestV1.json",
    "agent-run-completion-response.json": "domain/AgentRunCompletionV1.json",
    "agent-run-completion-running-status.json": (
        "domain/CompleteAgentRunRequestV1.json"
    ),
    "tool-response.json": "tools/ToolResponseV1.json",
    "tool-request-missing-consent-version.json": "tools/ToolRequestV1.json",
    "tool-response-missing-retryable.json": "tools/ToolResponseV1.json",
    "consent-create.json": "domain/CreateConsentRequestV1.json",
    "consent-create-without-confirmation.json": "domain/CreateConsentRequestV1.json",
    "companion-turn-request.json": "domain/CompanionTurnRequestV1.json",
    "companion-turn-response.json": "domain/CompanionTurnV1.json",
    "companion-turn-synthesis-capability-response.json": "domain/CompanionTurnV1.json",
    "companion-turn-request-extra-field.json": "domain/CompanionTurnRequestV1.json",
    "companion-turn-response-with-input.json": "domain/CompanionTurnV1.json",
    "companion-turn-synthesis-missing-text.json": "domain/CompanionTurnV1.json",
    "accountless-elder-create.json": "domain/CreateAccountlessElderRequestV1.json",
    "accountless-elder-created.json": "domain/AccountlessElderV1.json",
    "assisted-session-issue-request.json": "domain/IssueAssistedSessionRequestV1.json",
    "assisted-session-issued.json": "domain/IssuedAssistedSessionV1.json",
    "assisted-session-exchange.json": "domain/ExchangeAssistedSessionRequestV1.json",
    "assisted-session-activated.json": "domain/ActivatedAssistedSessionV1.json",
    "assisted-session-current.json": "domain/CurrentAssistedSessionV1.json",
    "assisted-first-use-acknowledge.json": "domain/AcknowledgeFirstUseRequestV1.json",
    "assisted-first-use-acknowledged.json": "domain/FirstUseAcknowledgementV1.json",
    "assisted-first-use-required.json": "domain/FirstUseAcknowledgementV1.json",
    "assisted-first-use-acknowledged-without-evidence.json": (
        "domain/FirstUseAcknowledgementV1.json"
    ),
    "assisted-companion-turn-request.json": "domain/AssistedCompanionTurnRequestV1.json",
    "assisted-session-ended.json": "domain/EndAssistedSessionV1.json",
    "care-action-create.json": "domain/CreateCareActionRequestV1.json",
    "care-action-update.json": "domain/UpdateCareActionRequestV1.json",
    "care-action.json": "domain/CareActionV1.json",
    "care-action-create-medical.json": "domain/CreateCareActionRequestV1.json",
    "care-action-update-without-reason.json": "domain/UpdateCareActionRequestV1.json",
    "voice-ticket-issue-request.json": "domain/CreateVoiceTicketRequestV1.json",
    "voice-ticket-issued-response.json": "domain/VoiceTicketIssuedV1.json",
    "voice-ticket-consume-request.json": "domain/ConsumeVoiceTicketRequestV1.json",
    "voice-ticket-issue-with-client-scope.json": (
        "domain/CreateVoiceTicketRequestV1.json"
    ),
    "voice-ticket-consume-with-actor.json": ("domain/ConsumeVoiceTicketRequestV1.json"),
    "speech-synthesis-capability-consume-request.json": (
        "domain/ConsumeSpeechSynthesisCapabilityRequestV1.json"
    ),
    "asr-result-submit.json": "domain/SubmitAsrResultRequestV1.json",
    "asr-gate-decision.json": "domain/AsrGateDecisionV1.json",
    "asr-gate-confirm.json": "domain/ConfirmAsrGateRequestV1.json",
    "asr-gate-decision-leaks-confidence.json": "domain/AsrGateDecisionV1.json",
    "asr-result-submit-with-ticket.json": "domain/SubmitAsrResultRequestV1.json",
    "care-event-candidate.json": "domain/CreateCareEventCandidateRequestV1.json",
    "care-event-candidate-with-transcript.json": "domain/CreateCareEventCandidateRequestV1.json",
    "care-event-candidate-evidence-must-be-opaque.json": (
        "domain/CreateCareEventCandidateRequestV1.json"
    ),
    "memory-candidate.json": "domain/CreateMemoryCandidateRequestV1.json",
    "memory-candidate-without-source.json": "domain/CreateMemoryCandidateRequestV1.json",
    "memory-confirm-elder-ui.json": "domain/ConfirmMemoryRequestV1.json",
    "memory-confirm-voice-without-evidence.json": "domain/ConfirmMemoryRequestV1.json",
    "memory-confirm-elder-voice.json": "domain/VoiceMemoryConfirmationRequestV1.json",
    "memory-confirm-voice-decision.json": "domain/VoiceMemoryDecisionV1.json",
    "memory-confirm-voice-decision-leaks-content.json": (
        "domain/VoiceMemoryDecisionV1.json"
    ),
    "memory-confirm-witness-missing-evidence.json": (
        "domain/VoiceMemoryConfirmationRequestV1.json"
    ),
    "summary-draft.json": "domain/CreateSummaryDraftRequestV1.json",
    "summary-draft-without-evidence-or-gap.json": "domain/CreateSummaryDraftRequestV1.json",
    "family-report-publish.json": "domain/PublishFamilyReportRequestV1.json",
    "family-report-publish-without-safety-review.json": (
        "domain/PublishFamilyReportRequestV1.json"
    ),
    "tool-request.json": "tools/ToolRequestV1.json",
    "tool-request-with-full-prompt.json": "tools/ToolRequestV1.json",
    "domain-event.json": "events/DomainEventEnvelopeV1.json",
    "domain-event-with-transcript.json": "events/DomainEventEnvelopeV1.json",
    "event-publisher-failure.json": "events/EventDeliveryFailureV1.json",
    "event-consumer-failure.json": "events/EventDeliveryFailureV1.json",
    "event-delivery-failure-with-raw-error.json": "events/EventDeliveryFailureV1.json",
    "event-delivery-failure-retry-at-limit.json": "events/EventDeliveryFailureV1.json",
    "rag-metadata.json": "rag/rag-metadata.schema.json",
    "rag-metadata-stop-normal-rag-string.json": "rag/rag-metadata.schema.json",
    "rag-chunk.json": "rag/rag-chunk.schema.json",
    "rag-chunk-missing-embedding-text.json": "rag/rag-chunk.schema.json",
    "ingestion-receipt.json": "rag/ingestion-receipt.schema.json",
    "ingestion-receipt-with-vectors.json": "rag/ingestion-receipt.schema.json",
    "rag-staging-embedding-authorization.json": (
        "rag/human-review-owner-acceptance-v2.schema.json"
    ),
    "rag-staging-embedding-authorization-production.json": (
        "rag/human-review-owner-acceptance-v2.schema.json"
    ),
    "retrieval-request.json": "rag/retrieval-request.schema.json",
    "retrieval-request-top-k-ten.json": "rag/retrieval-request.schema.json",
    "retrieval-response.json": "rag/retrieval-response.schema.json",
    "retrieval-response-missing-source-url.json": "rag/retrieval-response.schema.json",
    "retrieval-response-half-populated-page-range.json": "rag/retrieval-response.schema.json",
    "retrieval-request-v2.json": "rag/retrieval-request-v2.schema.json",
    "retrieval-response-v2.json": "rag/retrieval-response-v2.schema.json",
    "retrieval-response-v2-storage-url.json": ("rag/retrieval-response-v2.schema.json"),
    "retrieval-response-v2-missing-locator.json": (
        "rag/retrieval-response-v2.schema.json"
    ),
    "family-invitation-create-request.json": (
        "domain/CreateFamilyInvitationRequestV1.json"
    ),
    "family-invitation-create-duplicate-scope.json": (
        "domain/CreateFamilyInvitationRequestV1.json"
    ),
    "family-invitation-created-response.json": "domain/FamilyInvitationCreatedV1.json",
    "family-invitation-created-bad-code.json": "domain/FamilyInvitationCreatedV1.json",
    "family-invitation-list-response.json": "domain/FamilyInvitationListV1.json",
    "family-invitation-list-leaks-code.json": "domain/FamilyInvitationListV1.json",
    "family-invitation-revoked-response.json": "domain/FamilyInvitationStatusV1.json",
    "family-invitation-revoke-leaks-redeemer.json": (
        "domain/FamilyInvitationStatusV1.json"
    ),
    "line-link-challenge-create-request.json": "domain/CreateLineLinkChallengeRequestV1.json",
    "line-link-challenge-create-extra-field.json": "domain/CreateLineLinkChallengeRequestV1.json",
    "line-link-challenge-created-response.json": "domain/LineLinkChallengeCreatedV1.json",
    "line-link-status-response.json": "domain/LineLinkStatusV1.json",
    "line-link-status-leaks-subject.json": "domain/LineLinkStatusV1.json",
    "line-link-challenge-status-response.json": "domain/LineLinkChallengeStatusV1.json",
    "line-daily-notification-job-request.json": "domain/DailyLineNotificationJobRequestV1.json",
    "line-daily-notification-job-response.json": "domain/DailyLineNotificationJobResultV1.json",
    "line-daily-notification-job-leaks-content.json": (
        "domain/DailyLineNotificationJobRequestV1.json"
    ),
    "google-oidc-handoff-request.json": "domain/GoogleOidcHandoffRequestV1.json",
    "google-oidc-handoff-request-extra-token.json": (
        "domain/GoogleOidcHandoffRequestV1.json"
    ),
    "kinsun-email-auth-start-request.json": (
        "domain/StartKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-email-auth-start-response.json": "domain/StartedKinsunEmailAuthV1.json",
    "kinsun-email-auth-complete-request.json": (
        "domain/CompleteKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-password-login-request.json": "domain/PasswordLoginRequestV1.json",
    "kinsun-authenticated-response.json": "domain/CompletedKinsunEmailAuthV1.json",
    "kinsun-email-auth-start-with-scope.json": (
        "domain/StartKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-email-auth-complete-bad-code.json": (
        "domain/CompleteKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-password-login-with-actor.json": "domain/PasswordLoginRequestV1.json",
    "kinsun-authenticated-response-leaks-hash.json": (
        "domain/CompletedKinsunEmailAuthV1.json"
    ),
    "google-onboarding-complete-request.json": (
        "domain/CompleteGoogleOnboardingRequestV1.json"
    ),
    "google-onboarding-complete-bad-token.json": (
        "domain/CompleteGoogleOnboardingRequestV1.json"
    ),
    "line-oidc-handoff-request.json": "domain/LineOidcHandoffRequestV1.json",
    "line-oidc-handoff-request-extra-token.json": (
        "domain/LineOidcHandoffRequestV1.json"
    ),
    "line-onboarding-complete-request.json": (
        "domain/CompleteLineOnboardingRequestV1.json"
    ),
    "line-onboarding-complete-bad-token.json": (
        "domain/CompleteLineOnboardingRequestV1.json"
    ),
    "line-identity-link-request.json": "domain/LinkLineIdentityRequestV1.json",
    "line-identity-link-request-with-session.json": "domain/LinkLineIdentityRequestV1.json",
    "line-account-merge-confirm-request.json": (
        "domain/ConfirmLineAccountMergeRequestV1.json"
    ),
    "line-account-merge-confirm-raw-subject.json": (
        "domain/ConfirmLineAccountMergeRequestV1.json"
    ),
    "app-session-logout-response.json": "domain/AppSessionLogoutV1.json",
    "app-session-logout-response-leaks-token.json": ("domain/AppSessionLogoutV1.json"),
    "kinsun-email-start-request.json": ("domain/StartKinsunEmailAuthRequestV1.json"),
    "kinsun-email-start-request-provider-field.json": (
        "domain/StartKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-email-start-response.json": "domain/StartedKinsunEmailAuthV1.json",
    "kinsun-email-start-response-leaks-code.json": (
        "domain/StartedKinsunEmailAuthV1.json"
    ),
    "kinsun-email-complete-request.json": (
        "domain/CompleteKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-email-complete-request-extra-email.json": (
        "domain/CompleteKinsunEmailAuthRequestV1.json"
    ),
    "kinsun-password-login-request-session-token.json": (
        "domain/PasswordLoginRequestV1.json"
    ),
    "kinsun-authenticated-response-leaks-identity.json": (
        "domain/CompletedKinsunEmailAuthV1.json"
    ),
}

failures: list[str] = []


def load_registry() -> Registry:
    """Register every schema by its $id so cross-file $refs resolve."""
    registry = Registry()
    for path in sorted(SCHEMAS.rglob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            schema["$id"],
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
    return registry


def check_schemas(registry: Registry) -> None:
    for path in sorted(SCHEMAS.rglob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        rel = path.relative_to(CONTRACTS)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel}: not a valid JSON Schema: {exc}")
            continue
        print(f"ok    schema  {rel}")


def check_openapi() -> None:
    """Check every OpenAPI document under openapi/, not a hardcoded one.

    This used to name core-api.v1.yaml directly, which meant a second service's
    document would be silently skipped — worse than failing, because the gate
    would stay green while the contract went unchecked.
    """
    documents = sorted(p for p in (CONTRACTS / "openapi").glob("*.yaml"))
    if not documents:
        failures.append("openapi: no documents found")
    for path in documents:
        check_openapi_document(path)


def check_openapi_document(path: Path) -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))

    if doc.get("openapi") != "3.1.0":
        failures.append(f"openapi version is {doc.get('openapi')!r}, expected '3.1.0'")

    # Every local $ref (#/...) must resolve inside the document.
    def local_refs(node, trail="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str) and value.startswith("#/"):
                    yield value, trail
                else:
                    yield from local_refs(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                yield from local_refs(item, f"{trail}[{i}]")

    for ref, trail in local_refs(doc):
        cursor = doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(cursor, dict) or part not in cursor:
                failures.append(f"openapi: unresolved $ref {ref} at {trail}")
                break
            cursor = cursor[part]

    # Every external $ref must point at a file that exists.
    def external_refs(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if (
                    key == "$ref"
                    and isinstance(value, str)
                    and not value.startswith("#")
                ):
                    yield value
                else:
                    yield from external_refs(value)
        elif isinstance(node, list):
            for item in node:
                yield from external_refs(item)

    for ref in external_refs(doc):
        target = (path.parent / ref).resolve()
        if not target.is_file():
            failures.append(f"openapi: external $ref target missing: {ref}")

    paths = doc.get("paths", {})
    if path.name == "core-api.v1.yaml":
        speech_service_paths = {
            "/api/v1/internal/asr-results",
            "/api/v1/internal/elders/{elder_id}/memory-candidates/{memory_id}/voice-confirmation",
            "/api/v1/internal/speech-synthesis-capabilities/consume",
            "/api/v1/internal/voice-sessions/{session_id}/transition",
            "/api/v1/internal/voice-tickets/consume",
        }
        expected_security = [{"speechServiceCredential": []}]
        for speech_path in speech_service_paths:
            operation = paths.get(speech_path, {}).get("post", {})
            if operation.get("security") != expected_security:
                failures.append(
                    f"openapi: {speech_path} must require speechServiceCredential"
                )
        for api_path, path_item in paths.items():
            for method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                if (
                    operation.get("security") == expected_security
                    and api_path not in speech_service_paths
                ):
                    failures.append(
                        f"openapi: {method.upper()} {api_path} has over-broad "
                        "speechServiceCredential security"
                    )
    print(f"ok    openapi {path.name} ({len(paths)} paths)")
    for p in sorted(paths):
        print(f"        {p}")


def _refs(node, *, local: bool, trail: str = "$"):
    if isinstance(node, dict):
        for key, value in node.items():
            if (
                key == "$ref"
                and isinstance(value, str)
                and value.startswith("#/") is local
            ):
                yield value, trail
            else:
                yield from _refs(value, local=local, trail=f"{trail}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _refs(item, local=local, trail=f"{trail}[{index}]")


def _check_yaml_refs(doc: dict, path: Path, contract_name: str) -> None:
    for ref, trail in _refs(doc, local=True):
        cursor = doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(cursor, dict) or part not in cursor:
                failures.append(f"{contract_name}: unresolved $ref {ref} at {trail}")
                break
            cursor = cursor[part]

    for ref, trail in _refs(doc, local=False):
        file_part = ref.split("#", 1)[0]
        if not file_part:
            failures.append(
                f"{contract_name}: malformed external $ref {ref} at {trail}"
            )
            continue
        target = (path.parent / file_part).resolve()
        if not target.is_file():
            failures.append(
                f"{contract_name}: external $ref target missing at {trail}: {ref}"
            )


def check_asyncapi() -> None:
    asyncapi_dir = CONTRACTS / "asyncapi"
    documents = sorted(asyncapi_dir.glob("*.yaml"))
    if not documents:
        failures.append("asyncapi: no YAML contract found")
        return

    for path in documents:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            failures.append(f"asyncapi {path.name}: document root must be an object")
            continue
        version = str(doc.get("asyncapi", ""))
        if not version.startswith("3."):
            failures.append(
                f"asyncapi {path.name}: version is {version!r}, expected 3.x"
            )
        channels = doc.get("channels")
        operations = doc.get("operations")
        if not isinstance(channels, dict) or not channels:
            failures.append(
                f"asyncapi {path.name}: channels must be a non-empty object"
            )
        if not isinstance(operations, dict) or not operations:
            failures.append(
                f"asyncapi {path.name}: operations must be a non-empty object"
            )
        _check_yaml_refs(doc, path, f"asyncapi {path.name}")
        print(
            f"ok    asyncapi {path.name} "
            f"({len(channels) if isinstance(channels, dict) else 0} channels)"
        )


def _semantic_example_errors(schema_rel: str, payload: dict) -> list[str]:
    """Validate cross-field invariants JSON Schema cannot compare numerically."""
    if schema_rel != "events/EventDeliveryFailureV1.json":
        return []
    should_retry = (
        payload["retryable"] and payload["attempt_count"] < payload["max_attempts"]
    )
    expected = "RETRY" if should_retry else "DEAD_LETTER"
    if payload["disposition"] != expected:
        return [f"disposition must be {expected} for the attempt state"]
    return []


def check_examples(registry: Registry) -> None:
    for expect_valid, folder in ((True, "valid"), (False, "invalid")):
        for path in sorted((EXAMPLES / folder).glob("*.json")):
            schema_rel = DATA_SCHEMA_FOR.get(path.name)
            if schema_rel is None:
                failures.append(
                    f"{path.name}: no schema mapping declared in this validator"
                )
                continue

            schema = json.loads((SCHEMAS / schema_rel).read_text(encoding="utf-8"))
            payload = json.loads(path.read_text(encoding="utf-8"))["data"]
            validator = Draft202012Validator(
                schema,
                registry=registry,
                format_checker=FormatChecker(),
            )
            schema_errors = list(validator.iter_errors(payload))
            semantic_errors = _semantic_example_errors(schema_rel, payload)
            error_messages = [
                error.message for error in schema_errors
            ] + semantic_errors

            if expect_valid and error_messages:
                failures.append(
                    f"valid/{path.name}: should validate but did not: {error_messages[0]}"
                )
            elif not expect_valid and not error_messages:
                failures.append(
                    f"invalid/{path.name}: should have been REJECTED but validated cleanly — "
                    f"{schema_rel} is too permissive"
                )
            else:
                verdict = (
                    "accepted"
                    if expect_valid
                    else f"rejected ({error_messages[0][:60]})"
                )
                print(f"ok    example {folder}/{path.name}: {verdict}")


registry = load_registry()
check_schemas(registry)
check_openapi()
check_asyncapi()
check_examples(registry)

if failures:
    print("\nFAILURES:")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)

print("\nall contract checks passed")
