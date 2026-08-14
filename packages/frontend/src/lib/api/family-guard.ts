/**
 * Defence in depth for the family surface.
 *
 * MASTER.md §11 requires the family API client to intercept restricted fields
 * itself rather than trusting Core not to send them, and §10.3 requires that a
 * Draft / Needs-Review report is never rendered. Both are on the AGENTS.md §4
 * zero-tolerance list, so neither may rest on a single upstream check.
 *
 * These run on the RAW Core payload, before it is mapped to a view type —
 * mapping drops unknown keys, which would hide exactly the leak we want to see.
 */

import type { FamilyReportStatus } from './family-reports';

/**
 * Statuses a family member may see at all. Everything else is either not yet a
 * fact (DRAFT, NEEDS_REVIEW) or not a valid one (STALE).
 *
 * WITHDRAWN is included on purpose: §10.3 requires the withdrawal itself to be
 * visible. The card renders no items for it, so no withdrawn content leaks.
 */
const FAMILY_VISIBLE_STATUSES: ReadonlySet<string> = new Set<FamilyReportStatus>([
  'PUBLISHED',
  'WITHDRAWN',
]);

export function isFamilyVisibleStatus(status: string): boolean {
  return FAMILY_VISIBLE_STATUSES.has(status);
}

/**
 * MASTER.md §11's restricted list, normalised so a casing or camelCase change
 * upstream cannot slip past: keys are lowercased with `_` and `-` removed.
 */
const RESTRICTED_KEYS: ReadonlySet<string> = new Set([
  // 逐字稿
  'transcript',
  'transcripttext',
  'rawtranscript',
  'utterance',
  'utterancetext',
  // ASR 信心值
  'asrconfidence',
  'confidence',
  'confidenceband',
  'confidencescore',
  // 內部照護筆記
  'internalnote',
  'internalnotes',
  'carenote',
  'carenotes',
  'caregivernote',
  // 未覆核事件
  'unreviewedevents',
  'eventcandidates',
  'candidateevents',
  // 診斷式分數
  'riskscore',
  'healthscore',
  'emotionscore',
  'lonelinessscore',
  'diagnosis',
  'diagnosticscore',
  // 完整 Prompt
  'prompt',
  'systemprompt',
  'fullprompt',
  'promptversion',
]);

/** Bounds the walk so a cyclic or absurdly nested payload cannot hang the page. */
const MAX_DEPTH = 12;

function normaliseKey(key: string): string {
  return key.toLowerCase().replace(/[_-]/g, '');
}

export class FamilyDataRedlineError extends Error {
  constructor(public readonly field: string) {
    // The key NAME only. Never the value — AGENTS.md §8.1 forbids echoing a
    // rejected value back, and the value here is the restricted data itself.
    super(`Core returned a field the family surface must never receive: ${field}`);
    this.name = 'FamilyDataRedlineError';
  }
}

/**
 * Throws on the first restricted key found anywhere in `payload`.
 *
 * Hard failure is deliberate here, unlike the status filter below: a response
 * carrying a transcript means the contract is broken in a way we cannot bound,
 * so rendering the rest of it would be guessing about what else is wrong.
 */
export function assertNoRestrictedFields(payload: unknown, depth = 0): void {
  if (depth > MAX_DEPTH || payload === null || typeof payload !== 'object') return;

  if (Array.isArray(payload)) {
    for (const entry of payload) assertNoRestrictedFields(entry, depth + 1);
    return;
  }

  for (const [key, value] of Object.entries(payload)) {
    if (RESTRICTED_KEYS.has(normaliseKey(key))) {
      throw new FamilyDataRedlineError(key);
    }
    assertNoRestrictedFields(value, depth + 1);
  }
}

/**
 * Single-report counterpart used by both the list and detail clients below.
 *
 * Returns `null` rather than throwing: an unpublished report that never
 * reaches the DOM has leaked nothing, and the caller (list filter or detail
 * fetch) is what decides whether "not visible" means "drop this row" or
 * "treat the whole request as not found". The violation is still logged,
 * because silently swallowing it would hide a Core bug behind a page that
 * looks fine.
 *
 * Nothing is shown to the family about a dropped report — learning that a
 * draft exists is itself disclosure (§10.3).
 */
export function keepFamilyVisibleReport<T extends { status: string; report_id?: string }>(
  report: T,
): T | null {
  if (isFamilyVisibleStatus(report.status)) return report;
  // Status and id only: neither is restricted content, and the id is what
  // makes the Core-side bug findable.
  console.error(
    '[family] Core returned a report the family surface must not render; dropped it.',
    { status: report.status, reportId: report.report_id ?? '(unknown)' },
  );
  return null;
}

/** List counterpart of `keepFamilyVisibleReport`, used by `listFamilyReports`. */
export function keepFamilyVisible<T extends { status: string; report_id?: string }>(
  reports: readonly T[],
): T[] {
  const visible: T[] = [];
  for (const report of reports) {
    const kept = keepFamilyVisibleReport(report);
    if (kept) visible.push(kept);
  }
  return visible;
}
