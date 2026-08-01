"""Domain enums for the Identity & Elder Assignment module.

Defines all str-based enumerations used by ORM models and domain logic.

Every value here MUST exist in the eldercare_ai schema created by the Alembic
baseline — either as a label of the matching PostgreSQL ENUM type or as an
allowed value of the column's CHECK constraint. Adding a value here without a
migration produces a runtime error on INSERT, not a validation error.
"""

from enum import Enum


class ActorType(str, Enum):
    """Types of actors in the system.

    Mirrors eldercare_ai.actor_type_enum.

    Note there is deliberately no LEGAL_REPRESENTATIVE member: per document 06
    section 4.1 being a legal representative is a *relationship* to an elder,
    not a kind of actor. Such an actor is a FAMILY_MEMBER holding a
    RelationshipType.LEGAL_REPRESENTATIVE care relationship.
    """

    ELDER = "ELDER"
    DAYCARE_CARE_WORKER = "DAYCARE_CARE_WORKER"
    HOME_CARE_WORKER = "HOME_CARE_WORKER"
    FAMILY_MEMBER = "FAMILY_MEMBER"
    ADMIN = "ADMIN"
    CONTENT_MANAGER = "CONTENT_MANAGER"
    SYSTEM_SERVICE = "SYSTEM_SERVICE"


class ActorStatus(str, Enum):
    """Possible statuses for an Actor. Mirrors the actor.status CHECK."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class CareUnitType(str, Enum):
    """Types of care units. Mirrors eldercare_ai.care_unit_type_enum."""

    DAYCARE_CENTER = "DAYCARE_CENTER"
    COMMUNITY_SITE = "COMMUNITY_SITE"
    HOME_CARE_AGENCY = "HOME_CARE_AGENCY"


class PrimaryCareSetting(str, Enum):
    """Primary care setting for an Elder.

    Mirrors the elder.primary_care_setting CHECK constraint. There is no
    "BOTH": an elder attending a daycare centre while also receiving home care
    is modelled by two care relationships, not by a combined setting.
    """

    DAYCARE = "DAYCARE"
    COMMUNITY = "COMMUNITY"
    HOME_CARE = "HOME_CARE"
    INDEPENDENT = "INDEPENDENT"


class RelationshipType(str, Enum):
    """Types of care relationships between Actor and Elder.

    Mirrors eldercare_ai.relationship_type_enum.
    """

    DAYCARE_ASSIGNMENT = "DAYCARE_ASSIGNMENT"
    HOME_CARE_ASSIGNMENT = "HOME_CARE_ASSIGNMENT"
    FAMILY_SHARE = "FAMILY_SHARE"
    LEGAL_REPRESENTATIVE = "LEGAL_REPRESENTATIVE"


class RelationshipStatus(str, Enum):
    """Possible statuses for a CareRelationship.

    Mirrors the care_relationship.status CHECK constraint.
    """

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class AssignmentStatus(str, Enum):
    """Possible statuses for a CareAssignment.

    Mirrors the care_assignment.status CHECK constraint. A newly created
    assignment is DRAFT — the baseline has no SCHEDULED state.
    """

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class ElderScope(str, Enum):
    """Scope values for elder access control."""

    ELDER_BASIC_READ = "elder:basic:read"
    ELDER_SENSITIVE_READ = "elder:sensitive:read"
    ACCESS_CONTEXT_READ = "elder:access_context:read"
