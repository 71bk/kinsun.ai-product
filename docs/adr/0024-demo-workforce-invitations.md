# ADR 0024: Development workforce invitations

- Status: Accepted demo scope (2026-09-18, Owner requested an administrator invitation UI for demo)
- Extends Spec 19 / ADR 0015; does not enable public workforce registration.

An existing `ADMIN` with one current tenant membership may invite a new daycare or home-care
worker into an active care unit in that same tenant. The role must match the unit type.
The administrator copies a short-lived, single-use link; the recipient supplies the bound
email and chooses their own password. Manual delivery proves possession of the invitation,
not verification of an email inbox. This is development-only, behind
`STAFF_INVITATIONS_ENABLED=false`, and is rejected in production.

Store only a SHA-256 digest of a random 256-bit invitation credential and the existing keyed
email identity digest. The raw link is returned once, never stored in idempotency, audit or
outbox payloads. Its credential is carried in a URL fragment, removed from browser history
on load, and posted only to a same-origin BFF with origin validation. Acceptance rechecks
the issuer's live ADMIN membership, tenant, unit, expiry, status and recipient binding.
It cannot link or overwrite an existing identity or elevate an existing account.

Acceptance atomically consumes the invitation and creates Actor, Kinsun identity, Argon2id
credential, tenant membership, care-unit membership and minimal outbox audit. It grants no
elder Consent, relationship or home-care assignment. The recipient then uses the existing
password login. Issuance replay returns a conflict; the original credential is unrecoverable.
Revocation is version-bound and affects only invitations that have not been accepted.

The initial ADMIN is provisioned through an explicit development-only operator command,
not public registration. The UI cannot create administrators, change existing roles, reset
passwords or send email. Real email verification/delivery and production rollout remain deferred.
