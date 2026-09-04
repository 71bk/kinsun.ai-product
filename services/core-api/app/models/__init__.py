"""ORM models package.

Importing models here ensures they are registered with SQLAlchemy's
metadata when the application or Alembic imports this package.
"""

from app.models import enums  # noqa: F401
from app.models.account_merge import AccountMergeRequest  # noqa: F401
from app.models.actor import Actor  # noqa: F401
from app.models.agent import AgentRun, AgentToolCall  # noqa: F401
from app.models.app_session import AppSession  # noqa: F401
from app.models.asr_gate import AsrGateEvidence  # noqa: F401
from app.models.assisted_elder_session import AssistedElderSession  # noqa: F401
from app.models.care_action import CareAction  # noqa: F401
from app.models.care_action_candidate import (  # noqa: F401
    CareActionCandidate,
    CareActionCandidateEventProvenance,
)
from app.models.care_assignment import CareAssignment  # noqa: F401
from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision  # noqa: F401
from app.models.care_profile import ElderCareProfileEntry  # noqa: F401
from app.models.care_relationship import CareRelationship  # noqa: F401
from app.models.care_unit import CareUnit  # noqa: F401
from app.models.consent import ConsentGrant  # noqa: F401
from app.models.context_manifest import ContextManifest  # noqa: F401
from app.models.conversation import ConversationSession  # noqa: F401
from app.models.decision_support import DecisionSupportProfile  # noqa: F401
from app.models.deletion import (  # noqa: F401
    DeletionJobItem,
    DeletionRequest,
    DeletionTombstone,
)
from app.models.elder import Elder  # noqa: F401
from app.models.elder_enrollment import ElderEnrollment  # noqa: F401
from app.models.family_invitation import FamilyInvitation  # noqa: F401
from app.models.graph_projection import GraphProjectionRecord  # noqa: F401
from app.models.idempotency import IdempotencyRecord  # noqa: F401
from app.models.kinsun_identity import KinsunEmailChallenge  # noqa: F401
from app.models.knowledge import KnowledgeSource, KnowledgeSourceVersion  # noqa: F401
from app.models.line_identity import (  # noqa: F401
    ExternalIdentity,
    LineLinkChallenge,
    LineWebhookReceipt,
)
from app.models.membership import ActorTenantMembership  # noqa: F401
from app.models.memory import Memory, MemoryConfirmation, MemoryVersion  # noqa: F401
from app.models.notification import (  # noqa: F401
    NotificationDelivery,
    NotificationPreference,
)
from app.models.outbox import OutboxEvent  # noqa: F401
from app.models.password_credential import PasswordCredential  # noqa: F401
from app.models.pending_identity import PendingExternalIdentity  # noqa: F401
from app.models.policy import PolicyRegistry  # noqa: F401
from app.models.report import FamilyRelationship, FamilyReport, ReportVersion  # noqa: F401
from app.models.safety import SafetyEvaluation  # noqa: F401
from app.models.summary import DailySummary, SummaryVersion  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401
from app.models.transcript import TranscriptVersion  # noqa: F401
