"""Shared read visibility for professional daily summaries."""

FORMAL_SUMMARY_STATUSES = ("READY", "PUBLISHED")
ALLOWED_SUMMARY_STATUSES = frozenset(
    {"DRAFT", "READY", "NEEDS_REVIEW", "PUBLISHED", "STALE", "WITHDRAWN"}
)
