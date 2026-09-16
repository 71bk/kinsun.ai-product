# Pending branch closeout — 2026-09-16

Base: `origin/main` at `38047f6` (PR #52). The owner requested handling all remaining
unmerged branches. Current changes were integrated on a fresh branch from main.

## Disposition

| Branch / original head | Resolution |
| --- | --- |
| `feat/frontend-polish-followups-20260916` / `3042b81` | Integrated: shared, visible family sign-in labels and localized copy; quieter elder start-page background and shadows. |
| `qa/b03-b04-real-auth-20260916` / `320cf2b` | Integrated both pending commits: development migration evidence and retired real-auth campaign evidence, guarded helper and offline safety tests. |
| `ops/b03-b04-development-migration-20260916` / `f10027c` | Duplicate: patch-equivalent to `b058de1`, already included through the QA branch. |
| `feat/b03-b04-event-frontend` / `6b5448e` | Already incorporated by merged PR #51; retain the worktree directory while updating its clean checkout. |
| `feat/wave2-l02-runtime-validation` / `585c496` | Superseded by current response-envelope guards and 82 client tests. Preserve original history under `archive/wave2-l02-runtime-validation-20260916`. |
| `origin/feature/line-account-linking` / `d4c5dba` | Retire historical branch; preserve full history under `archive/line-account-linking-20260916`. |

Both archive tags were pushed to origin before branch deletion. They preserve commits
that are intentionally not ancestors of main; archiving does not claim a Git merge.

## Why the historical implementations were not reintroduced

The current API client validates separate Core/BFF envelopes, calendar/timezone values,
error details and authentication/authorization status handling. The older L02 patch
would replace these later improvements with its earlier inline guards.

Current LINE linking, webhook, notification services, contracts, rich-menu assets and
frontend routes remain present. LINE delivery schema is represented by the current
baseline and `20260810_1000_add_line_delivery_foundation.py`. The historical branch also
contains obsolete Cognito callbacks, old migration history and AWS infrastructure.
Its wholesale merge would conflict with [ADR 0010](../adr/0010-provider-neutral-oidc-and-application-sessions.md)
and [ADR 0019](../adr/0019-retire-aws-cdk-deployment-profile.md).

## Validation on the integrated code

- Frontend: 610 tests across 65 files; typecheck, production build and ESLint passed.
- Imported QA helper: 13 offline safety tests, Ruff check and Node syntax check passed.
- CI impact rules: 26 tests passed. Evidence JSON parsed and checked for credential
  fields, session-token values and database URLs; none found.
- Playwright production UI: family sign-in in `zh-Hant` and `en`, and elder login and
  registration, at 375×812, 390×844, 430×932 and 1440×900. All 16 screenshots inspected;
  no horizontal overflow or clipped controls. Family labels and password visibility
  toggle passed; elder keyboard tab navigation also passed with reduced motion enabled.
- Screenshots stay local under `.qa/local/closeout-family-*.png` and
  `.qa/local/closeout-elder-*.png`. Focus rings are expected focused-control styling.
  The initial QA locator used a translated email label, while the actual shared label
  is `Email` in both languages; correcting the locator required no product change.
- This pass did not submit login/registration forms, recreate the retired campaign,
  change database state, or claim real-device or deployed-environment acceptance.

Historical B03/B04 live acceptance remains described in
[the original report](b03-b04-real-auth-20260916.md). Its campaign is retired and must
not be reused. This closeout adds no migrations and does not close remaining Wave 2
product gaps. PR CI and merge status are recorded by the associated GitHub PR.
