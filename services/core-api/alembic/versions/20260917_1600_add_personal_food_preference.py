"""Allow an explicit self-stated food preference; no existing memory activation.

Revision ID: b6d8f0a2c435
Revises: a5c7e9f1b324
"""

from alembic import op

revision = "b6d8f0a2c435"
down_revision = "a5c7e9f1b324"
branch_labels = None
depends_on = None

_KINDS = (
    "'MUSIC_PREFERENCE','HOBBY','PREFERRED_ADDRESS','FAMILY_RELATIONSHIP',"
    "'CONTACT_ROUTINE','DAILY_ROUTINE','HEALTH_INFERENCE','MEDICATION_JUDGMENT',"
    "'MOOD_OR_LONELINESS_INFERENCE','FAMILY_CONFLICT','FINANCIAL_INFORMATION',"
    "'SENSITIVE_OR_UNKNOWN'"
)


def _constraint(kinds: str) -> None:
    op.drop_constraint("ck_memory_kind", "memory", schema="eldercare_ai", type_="check")
    op.create_check_constraint(
        "ck_memory_kind",
        "memory",
        f"memory_kind IS NULL OR memory_kind IN ({kinds})",
        schema="eldercare_ai",
    )


def upgrade() -> None:
    _constraint(_KINDS + ",'FOOD_PREFERENCE'")


def downgrade() -> None:
    # PostgreSQL validates the narrowed constraint; existing new-kind data blocks downgrade.
    _constraint(_KINDS)
