'use client';

import {
  CheckCircle,
  Clock,
  PauseCircle,
  Play,
  Prohibit,
  Plus,
  Sparkle,
  X,
} from '@phosphor-icons/react';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Toast } from '@/components/ui/Toast';
import {
  adoptCareActionCandidate,
  createCareAction,
  dismissCareActionCandidate,
  listCareActionCandidates,
  listCareActions,
  updateCareAction,
  type CareActionCandidateDecision,
  type CareActionCandidateView,
  type CareActionPriority,
  type CareActionStatus,
  type CareActionTransition,
  type CareActionType,
  type CareActionView,
} from '@/lib/api/care-actions';
import { ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { listEvents, type EventView } from '@/lib/api/events';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import {
  appendCareActionCandidatePage,
  appendCareActionPage,
  mergeFormalEventPages,
} from './care-action-pagination';
import styles from './CareActionPanel.module.css';

const ACTION_TYPES: CareActionType[] = [
  'CONTACT_ELDER',
  'CONTACT_FAMILY',
  'CONFIRM_INFORMATION',
  'INVITE_ACTIVITY',
  'FOLLOW_UP',
  'OTHER',
];
const PRIORITIES: CareActionPriority[] = ['LOW', 'MEDIUM', 'HIGH'];

const STATUS_ICON = {
  OPEN: Clock,
  IN_PROGRESS: Play,
  COMPLETED: CheckCircle,
  POSTPONED: PauseCircle,
  CANCELLED: Prohibit,
} satisfies Record<CareActionStatus, typeof Clock>;

const TRANSITIONS: Record<CareActionStatus, CareActionTransition[]> = {
  OPEN: ['IN_PROGRESS', 'COMPLETED', 'POSTPONED', 'CANCELLED'],
  IN_PROGRESS: ['COMPLETED', 'POSTPONED', 'CANCELLED'],
  POSTPONED: ['IN_PROGRESS', 'COMPLETED', 'CANCELLED'],
  COMPLETED: [],
  CANCELLED: [],
};

const TRANSITION_LABEL: Record<CareActionTransition, MessageKey> = {
  IN_PROGRESS: 'careAction.start',
  COMPLETED: 'careAction.complete',
  POSTPONED: 'careAction.postpone',
  CANCELLED: 'careAction.cancelAction',
};

function defaultDueLocal(): string {
  const due = new Date();
  due.setDate(due.getDate() + 1);
  due.setHours(9, 0, 0, 0);
  return new Date(due.getTime() - due.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function minimumDueLocal(): string {
  const due = new Date(Date.now() + 5 * 60_000);
  return new Date(due.getTime() - due.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function toLocalDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || date.getTime() <= Date.now() + 5 * 60_000) {
    return defaultDueLocal();
  }
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function describeActionError(error: unknown, fallback: MessageKey): MessageKey {
  if (error instanceof ApiRequestError && error.status === 409) return 'error.versionConflict';
  if (error instanceof ApiRequestError && (error.status === 403 || error.status === 404)) {
    return 'error.noElderDataPermission';
  }
  return fallback;
}

type FormalEventStatus = 'VERIFIED' | 'CORRECTED';

const FORMAL_EVENT_STATUSES: FormalEventStatus[] = ['VERIFIED', 'CORRECTED'];

function emptySourceCursors(): Record<FormalEventStatus, string | null> {
  return { VERIFIED: null, CORRECTED: null };
}

export interface CareActionPanelProps {
  apiConfig: ApiConfig;
  elderId: string;
  canCreate: boolean;
  canUpdate: boolean;
}

export function CareActionPanel({
  apiConfig,
  elderId,
  canCreate,
  canUpdate,
}: CareActionPanelProps) {
  const { t, formatDateTime } = useLocale();
  const [actions, setActions] = useState<CareActionView[]>([]);
  const [candidates, setCandidates] = useState<CareActionCandidateView[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [candidateHasMore, setCandidateHasMore] = useState(false);
  const [candidateNextCursor, setCandidateNextCursor] = useState<string | null>(null);
  const [formalEvents, setFormalEvents] = useState<EventView[]>([]);
  const [sourceCursors, setSourceCursors] = useState(emptySourceCursors);
  const [loading, setLoading] = useState(true);
  const [candidatesLoading, setCandidatesLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [candidatesLoadingMore, setCandidatesLoadingMore] = useState(false);
  const [sourcesLoading, setSourcesLoading] = useState(canCreate);
  const [sourcesLoadingMore, setSourcesLoadingMore] = useState(false);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);
  const [toastKey, setToastKey] = useState<MessageKey | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [transitionBusy, setTransitionBusy] = useState(false);
  const [candidateBusyId, setCandidateBusyId] = useState<string | null>(null);
  const [pendingAdoption, setPendingAdoption] = useState<{
    candidate: CareActionCandidateView;
    title: string;
    dueAt: string;
    priority: CareActionPriority;
  } | null>(null);
  const [pendingDismissal, setPendingDismissal] = useState<{
    candidate: CareActionCandidateView;
    decision: CareActionCandidateDecision;
  } | null>(null);
  const [dismissReasonCode, setDismissReasonCode] = useState('NOT_NEEDED');
  const [dismissNotes, setDismissNotes] = useState('');
  const [pendingTransition, setPendingTransition] = useState<{
    action: CareActionView;
    status: Exclude<CareActionTransition, 'IN_PROGRESS'>;
  } | null>(null);
  const [confirmStart, setConfirmStart] = useState<CareActionView | null>(null);
  const [resolution, setResolution] = useState('');
  const [newDueAt, setNewDueAt] = useState(defaultDueLocal);

  const loadActions = useCallback(async () => {
    setLoading(true);
    setErrorKey(null);
    setActions([]);
    setHasMore(false);
    setNextCursor(null);
    try {
      const result = await listCareActions(apiConfig, elderId);
      setActions(result.items);
      setHasMore(result.hasMore);
      setNextCursor(result.nextCursor);
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.loadCareActionsFailed'));
    } finally {
      setLoading(false);
    }
  }, [apiConfig, elderId]);

  const loadCandidates = useCallback(async () => {
    setCandidatesLoading(true);
    setCandidates([]);
    setCandidateHasMore(false);
    setCandidateNextCursor(null);
    try {
      const result = await listCareActionCandidates(apiConfig, elderId);
      setCandidates(result.items);
      setCandidateHasMore(result.hasMore);
      setCandidateNextCursor(result.nextCursor);
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.loadCareActionCandidatesFailed'));
    } finally {
      setCandidatesLoading(false);
    }
  }, [apiConfig, elderId]);

  const loadSources = useCallback(async () => {
    if (!canCreate) return;
    setSourcesLoading(true);
    setFormalEvents([]);
    setSourceCursors(emptySourceCursors());
    try {
      const [verified, corrected] = await Promise.all([
        listEvents(apiConfig, elderId, { status: 'VERIFIED' }),
        listEvents(apiConfig, elderId, { status: 'CORRECTED' }),
      ]);
      setFormalEvents(mergeFormalEventPages([], [...verified.items, ...corrected.items]));
      setSourceCursors({
        VERIFIED: verified.nextCursor,
        CORRECTED: corrected.nextCursor,
      });
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.loadEventsFailed'));
    } finally {
      setSourcesLoading(false);
    }
  }, [apiConfig, canCreate, elderId]);

  async function loadMoreActions() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setErrorKey(null);
    try {
      const result = await listCareActions(apiConfig, elderId, { cursor: nextCursor });
      setActions((current) => appendCareActionPage(current, result.items));
      setHasMore(result.hasMore);
      setNextCursor(result.nextCursor);
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.loadCareActionsFailed'));
    } finally {
      setLoadingMore(false);
    }
  }

  async function loadMoreCandidates() {
    if (!candidateNextCursor || candidatesLoadingMore) return;
    setCandidatesLoadingMore(true);
    setErrorKey(null);
    try {
      const result = await listCareActionCandidates(apiConfig, elderId, {
        cursor: candidateNextCursor,
      });
      setCandidates((current) => appendCareActionCandidatePage(current, result.items));
      setCandidateHasMore(result.hasMore);
      setCandidateNextCursor(result.nextCursor);
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.loadCareActionCandidatesFailed'));
    } finally {
      setCandidatesLoadingMore(false);
    }
  }

  async function loadMoreSources() {
    if (sourcesLoadingMore) return;
    const pendingStatuses = FORMAL_EVENT_STATUSES.filter((status) => sourceCursors[status]);
    if (pendingStatuses.length === 0) return;

    setSourcesLoadingMore(true);
    setErrorKey(null);
    try {
      const pages = await Promise.all(
        pendingStatuses.map(async (status) => ({
          status,
          result: await listEvents(apiConfig, elderId, {
            status,
            cursor: sourceCursors[status] ?? undefined,
          }),
        })),
      );
      setFormalEvents((current) =>
        mergeFormalEventPages(
          current,
          pages.flatMap((page) => page.result.items),
        ),
      );
      setSourceCursors((current) => {
        const updated = { ...current };
        for (const page of pages) updated[page.status] = page.result.nextCursor;
        return updated;
      });
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.loadEventsFailed'));
    } finally {
      setSourcesLoadingMore(false);
    }
  }

  useEffect(() => {
    void loadActions();
  }, [loadActions]);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  const sourceHasMore = FORMAL_EVENT_STATUSES.some((status) => sourceCursors[status] !== null);

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setCreateBusy(true);
    setErrorKey(null);
    try {
      const created = await createCareAction(apiConfig, elderId, {
        actionType: String(form.get('actionType')) as CareActionType,
        title: String(form.get('title')),
        description: String(form.get('description')),
        triggerReason: String(form.get('triggerReason')),
        relatedEventIds: [String(form.get('sourceEvent'))],
        dueAt: new Date(String(form.get('dueAt'))).toISOString(),
        priority: String(form.get('priority')) as CareActionPriority,
      });
      setActions((current) => [created, ...current]);
      setShowCreate(false);
      formElement.reset();
      setToastKey('toast.careActionCreated');
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.createCareActionFailed'));
    } finally {
      setCreateBusy(false);
    }
  }

  async function runTransition(
    action: CareActionView,
    status: CareActionTransition,
    transitionResolution?: string,
    dueAt?: string,
  ) {
    setTransitionBusy(true);
    setErrorKey(null);
    try {
      const updated = await updateCareAction(apiConfig, elderId, action, {
        status,
        resolution: transitionResolution,
        dueAt: dueAt ? new Date(dueAt).toISOString() : undefined,
      });
      setActions((current) =>
        current.map((item) => (item.careActionId === updated.careActionId ? updated : item)),
      );
      setPendingTransition(null);
      setConfirmStart(null);
      setResolution('');
      setNewDueAt(defaultDueLocal());
      setToastKey('toast.careActionUpdated');
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.updateCareActionFailed'));
    } finally {
      setTransitionBusy(false);
    }
  }

  function selectTransition(action: CareActionView, status: CareActionTransition) {
    if (status === 'IN_PROGRESS') {
      setConfirmStart(action);
      return;
    }
    setResolution('');
    setNewDueAt(defaultDueLocal());
    setPendingTransition({ action, status });
  }

  function openAdoption(candidate: CareActionCandidateView) {
    setPendingDismissal(null);
    setPendingAdoption({
      candidate,
      title: candidate.suggestedTitle,
      dueAt: toLocalDateTime(candidate.suggestedDueAt),
      priority: candidate.priority,
    });
  }

  function openDismissal(
    candidate: CareActionCandidateView,
    decision: CareActionCandidateDecision,
  ) {
    setPendingAdoption(null);
    setDismissReasonCode('NOT_NEEDED');
    setDismissNotes('');
    setPendingDismissal({ candidate, decision });
  }

  async function runAdoption() {
    if (!pendingAdoption) return;
    const { candidate, title, dueAt, priority } = pendingAdoption;
    setCandidateBusyId(candidate.careActionCandidateId);
    setErrorKey(null);
    try {
      await adoptCareActionCandidate(apiConfig, elderId, candidate, {
        title,
        dueAt: new Date(dueAt).toISOString(),
        priority,
      });
      setCandidates((current) =>
        current.filter((item) => item.careActionCandidateId !== candidate.careActionCandidateId),
      );
      setPendingAdoption(null);
      await loadActions();
      setToastKey('toast.careActionCandidateAdopted');
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.adoptCareActionCandidateFailed'));
    } finally {
      setCandidateBusyId(null);
    }
  }

  async function runDismissal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingDismissal) return;
    const { candidate, decision } = pendingDismissal;
    setCandidateBusyId(candidate.careActionCandidateId);
    setErrorKey(null);
    try {
      await dismissCareActionCandidate(apiConfig, elderId, candidate, {
        decision,
        reasonCode: dismissReasonCode,
        notes: dismissNotes,
      });
      setCandidates((current) =>
        current.filter((item) => item.careActionCandidateId !== candidate.careActionCandidateId),
      );
      setPendingDismissal(null);
      setDismissNotes('');
      setToastKey('toast.careActionCandidateDismissed');
    } catch (error) {
      setErrorKey(describeActionError(error, 'error.dismissCareActionCandidateFailed'));
    } finally {
      setCandidateBusyId(null);
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>{t('careAction.heading')}</h2>
          <p>{t('careAction.intro')}</p>
        </div>
        {canCreate && formalEvents.length > 0 && (
          <button
            aria-expanded={showCreate}
            className={styles.createToggle}
            onClick={() => setShowCreate((current) => !current)}
            type="button"
          >
            {showCreate ? (
              <X aria-hidden="true" size={20} weight="bold" />
            ) : (
              <Plus aria-hidden="true" size={20} weight="bold" />
            )}
            {t(showCreate ? 'careAction.closeForm' : 'careAction.create')}
          </button>
        )}
      </div>

      {errorKey && <ErrorState description={t(errorKey)} />}

      <section aria-labelledby="care-action-candidate-heading" className={styles.candidateSection}>
        <div className={styles.candidateHeader}>
          <div>
            <div className={styles.candidateTitleRow}>
              <Sparkle aria-hidden="true" size={22} weight="fill" />
              <h3 id="care-action-candidate-heading">
                {t('careAction.candidateHeading', { count: candidates.length })}
              </h3>
            </div>
            <p>{t('careAction.candidateIntro')}</p>
          </div>
          <span className={styles.candidateBoundary}>{t('careAction.candidateBoundary')}</span>
        </div>

        {candidatesLoading ? (
          <Skeleton rows={2} />
        ) : candidates.length === 0 ? (
          <p className={styles.candidateEmpty}>{t('careAction.candidateEmpty')}</p>
        ) : (
          <div className={styles.candidateList}>
            {candidates.map((candidate) => {
              const dismissing =
                pendingDismissal?.candidate.careActionCandidateId ===
                candidate.careActionCandidateId;
              const busy = candidateBusyId === candidate.careActionCandidateId;
              return (
                <article className={styles.candidateCard} key={candidate.careActionCandidateId}>
                  <div className={styles.cardHeader}>
                    <div>
                      <span className={styles.type}>
                        {t(`careActionType.${candidate.actionType}` as MessageKey)}
                      </span>
                      <h4>{candidate.suggestedTitle}</h4>
                    </div>
                    <span className={styles.candidateBadge}>
                      <Sparkle aria-hidden="true" size={16} weight="fill" />
                      {t('careAction.candidateBadge')}
                    </span>
                  </div>
                  <p className={styles.candidateReason}>{candidate.triggerReason}</p>
                  <dl className={styles.details}>
                    <div>
                      <dt>{t('careAction.priority')}</dt>
                      <dd>{t(`careActionPriority.${candidate.priority}` as MessageKey)}</dd>
                    </div>
                    <div>
                      <dt>{t('careAction.candidateSuggestedDue')}</dt>
                      <dd>{formatDateTime(candidate.suggestedDueAt)}</dd>
                    </div>
                    <div className={styles.fullWidth}>
                      <dt>
                        {t('careAction.candidateSources', {
                          count: candidate.sourceEventProvenance.length,
                        })}
                      </dt>
                      <dd>
                        {candidate.sourceEventProvenance
                          .map((source) =>
                            t('careAction.candidateSource', {
                              type: t(`eventType.${source.eventType}` as MessageKey),
                              version: source.eventVersion,
                            }),
                          )
                          .join(' · ')}
                      </dd>
                    </div>
                  </dl>
                  {!dismissing && (canCreate || canUpdate) && (
                    <div className={styles.candidateActions}>
                      {canUpdate && (
                        <>
                          <button
                            className={styles.destructiveButton}
                            disabled={candidateBusyId !== null}
                            onClick={() => openDismissal(candidate, 'REJECT')}
                            type="button"
                          >
                            {t('careAction.candidateReject')}
                          </button>
                          <button
                            className={styles.secondaryButton}
                            disabled={candidateBusyId !== null}
                            onClick={() => openDismissal(candidate, 'EXCLUDE')}
                            type="button"
                          >
                            {t('careAction.candidateExclude')}
                          </button>
                        </>
                      )}
                      {canCreate && (
                        <button
                          className={styles.primaryButton}
                          disabled={candidateBusyId !== null}
                          onClick={() => openAdoption(candidate)}
                          type="button"
                        >
                          {t('careAction.candidateAdopt')}
                        </button>
                      )}
                    </div>
                  )}
                  {dismissing && pendingDismissal && (
                    <form
                      className={styles.transitionForm}
                      onSubmit={(event) => void runDismissal(event)}
                    >
                      <h4>
                        {t(
                          pendingDismissal.decision === 'REJECT'
                            ? 'careAction.candidateRejectHeading'
                            : 'careAction.candidateExcludeHeading',
                        )}
                      </h4>
                      <label className={styles.field}>
                        <span>{t('careAction.candidateDismissReason')}</span>
                        <select
                          disabled={busy}
                          onChange={(event) => setDismissReasonCode(event.target.value)}
                          value={dismissReasonCode}
                        >
                          <option value="NOT_NEEDED">
                            {t('careAction.candidateReasonNotNeeded')}
                          </option>
                          <option value="ALREADY_HANDLED">
                            {t('careAction.candidateReasonAlreadyHandled')}
                          </option>
                          <option value="SOURCE_INSUFFICIENT">
                            {t('careAction.candidateReasonSourceInsufficient')}
                          </option>
                          <option value="OUT_OF_SCOPE">
                            {t('careAction.candidateReasonOutOfScope')}
                          </option>
                        </select>
                      </label>
                      <label className={styles.field}>
                        <span>{t('careAction.candidateDismissNotes')}</span>
                        <textarea
                          disabled={busy}
                          maxLength={2000}
                          onChange={(event) => setDismissNotes(event.target.value)}
                          rows={3}
                          value={dismissNotes}
                        />
                      </label>
                      <div className={styles.formActions}>
                        <button
                          className={styles.secondaryButton}
                          disabled={busy}
                          onClick={() => setPendingDismissal(null)}
                          type="button"
                        >
                          {t('common.cancel')}
                        </button>
                        <button
                          className={
                            pendingDismissal.decision === 'REJECT'
                              ? styles.destructiveButton
                              : styles.primaryButton
                          }
                          disabled={busy}
                          type="submit"
                        >
                          {t('careAction.candidateDismissSubmit')}
                        </button>
                      </div>
                    </form>
                  )}
                </article>
              );
            })}
            {candidateHasMore && (
              <div className={styles.pagination}>
                <p aria-live="polite" className={styles.notice}>
                  {t('careAction.candidateListLimited')}
                </p>
                <button
                  className={styles.secondaryButton}
                  disabled={candidatesLoadingMore || candidateNextCursor === null}
                  onClick={() => void loadMoreCandidates()}
                  type="button"
                >
                  {t(
                    candidatesLoadingMore
                      ? 'careAction.loadingMoreCandidates'
                      : 'careAction.loadMoreCandidates',
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      {canCreate && !sourcesLoading && formalEvents.length === 0 && (
        <EmptyState
          description={t('careAction.noSourceDescription')}
          title={t('careAction.noSourceTitle')}
        />
      )}

      {showCreate && (
        <form className={styles.createForm} onSubmit={(event) => void submitCreate(event)}>
          <h3>{t('careAction.formHeading')}</h3>
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{t('careAction.type')}</span>
              <select defaultValue="FOLLOW_UP" name="actionType">
                {ACTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`careActionType.${type}` as MessageKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>{t('careAction.priority')}</span>
              <select defaultValue="MEDIUM" name="priority">
                {PRIORITIES.map((priority) => (
                  <option key={priority} value={priority}>
                    {t(`careActionPriority.${priority}` as MessageKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className={`${styles.field} ${styles.fullWidth}`}>
              <span>{t('careAction.title')}</span>
              <input maxLength={200} name="title" required />
            </label>
            <label className={`${styles.field} ${styles.fullWidth}`}>
              <span>{t('careAction.description')}</span>
              <textarea maxLength={4000} name="description" rows={3} />
            </label>
            <label className={`${styles.field} ${styles.fullWidth}`}>
              <span>{t('careAction.reason')}</span>
              <textarea maxLength={2000} name="triggerReason" required rows={3} />
            </label>
            <label className={`${styles.field} ${styles.fullWidth}`}>
              <span>{t('careAction.sourceEvent')}</span>
              <select name="sourceEvent" required>
                {formalEvents.map((source) => (
                  <option key={source.eventId} value={source.eventId}>
                    {t('careAction.sourceOption', {
                      date: source.eventDate,
                      type: t(`eventType.${source.eventType}` as MessageKey),
                      content: source.content,
                    })}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>{t('careAction.dueAt')}</span>
              <input
                defaultValue={defaultDueLocal()}
                min={minimumDueLocal()}
                name="dueAt"
                required
                type="datetime-local"
              />
            </label>
          </div>
          {sourceHasMore && (
            <div className={styles.pagination}>
              <p aria-live="polite" className={styles.notice}>
                {t('careAction.sourceLimited')}
              </p>
              <button
                className={styles.secondaryButton}
                disabled={sourcesLoadingMore}
                onClick={() => void loadMoreSources()}
                type="button"
              >
                {t(
                  sourcesLoadingMore
                    ? 'careAction.loadingMoreSources'
                    : 'careAction.loadMoreSources',
                )}
              </button>
            </div>
          )}
          <div className={styles.formActions}>
            <button
              className={styles.secondaryButton}
              disabled={createBusy}
              onClick={() => setShowCreate(false)}
              type="button"
            >
              {t('common.cancel')}
            </button>
            <button className={styles.primaryButton} disabled={createBusy} type="submit">
              {t(createBusy ? 'careAction.submitting' : 'careAction.submit')}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <Skeleton rows={5} />
      ) : actions.length === 0 ? (
        <EmptyState
          description={t('careAction.emptyDescription')}
          title={t('careAction.emptyTitle')}
        />
      ) : (
        <div className={styles.list}>
          {hasMore && (
            <div className={styles.pagination}>
              <p aria-live="polite" className={styles.notice}>
                {t('careAction.listLimited')}
              </p>
              <button
                className={styles.secondaryButton}
                disabled={loadingMore || nextCursor === null}
                onClick={() => void loadMoreActions()}
                type="button"
              >
                {t(loadingMore ? 'careAction.loadingMoreActions' : 'careAction.loadMoreActions')}
              </button>
            </div>
          )}
          {actions.map((action) => {
            const Icon = STATUS_ICON[action.status];
            const availableTransitions = canUpdate ? TRANSITIONS[action.status] : [];
            const editing = pendingTransition?.action.careActionId === action.careActionId;
            return (
              <article
                className={styles.card}
                data-status={action.status}
                key={action.careActionId}
              >
                <div className={styles.cardHeader}>
                  <div>
                    <span className={styles.type}>
                      {t(`careActionType.${action.actionType}` as MessageKey)}
                    </span>
                    <h3>{action.title}</h3>
                  </div>
                  <div className={styles.status}>
                    <Icon aria-hidden="true" size={20} weight="bold" />
                    <span>{t(`careActionStatus.${action.status}` as MessageKey)}</span>
                  </div>
                </div>
                {action.description && <p>{action.description}</p>}
                <dl className={styles.details}>
                  <div>
                    <dt>{t('careAction.priority')}</dt>
                    <dd>{t(`careActionPriority.${action.priority}` as MessageKey)}</dd>
                  </div>
                  <div>
                    <dt>{t('careAction.dueAt')}</dt>
                    <dd>{formatDateTime(action.dueAt)}</dd>
                  </div>
                  <div className={styles.fullWidth}>
                    <dt>{t('careAction.triggerReason')}</dt>
                    <dd>{action.triggerReason ?? t('common.empty')}</dd>
                  </div>
                  <div>
                    <dt>{t('careAction.sources', { count: action.relatedEventIds.length })}</dt>
                    <dd>{action.relatedEventIds.map((id) => id.slice(0, 8)).join(' · ')}</dd>
                  </div>
                  <div>
                    <dt>{t('careAction.assignedSelf')}</dt>
                    <dd>{t('common.version', { version: action.version })}</dd>
                  </div>
                </dl>
                {action.resolution && (
                  <p className={styles.resolution}>
                    {t('careAction.resolution', { resolution: action.resolution })}
                  </p>
                )}
                <p className={styles.createdAt}>
                  {t('careAction.createdAt', { at: formatDateTime(action.createdAt) })}
                </p>
                {availableTransitions.length > 0 && !editing && (
                  <div className={styles.transitionActions}>
                    {availableTransitions.map((status) => (
                      <button
                        className={
                          status === 'CANCELLED' ? styles.destructiveButton : styles.secondaryButton
                        }
                        disabled={transitionBusy}
                        key={status}
                        onClick={() => selectTransition(action, status)}
                        type="button"
                      >
                        {t(TRANSITION_LABEL[status])}
                      </button>
                    ))}
                  </div>
                )}
                {editing && pendingTransition && (
                  <form
                    className={styles.transitionForm}
                    onSubmit={(event) => {
                      event.preventDefault();
                      void runTransition(
                        action,
                        pendingTransition.status,
                        resolution,
                        pendingTransition.status === 'POSTPONED' ? newDueAt : undefined,
                      );
                    }}
                  >
                    <label className={styles.field}>
                      <span>{t('careAction.transitionReason')}</span>
                      <textarea
                        disabled={transitionBusy}
                        maxLength={2000}
                        onChange={(event) => setResolution(event.target.value)}
                        required
                        rows={3}
                        value={resolution}
                      />
                    </label>
                    {pendingTransition.status === 'POSTPONED' && (
                      <label className={styles.field}>
                        <span>{t('careAction.transitionDueAt')}</span>
                        <input
                          disabled={transitionBusy}
                          min={minimumDueLocal()}
                          onChange={(event) => setNewDueAt(event.target.value)}
                          required
                          type="datetime-local"
                          value={newDueAt}
                        />
                      </label>
                    )}
                    <div className={styles.formActions}>
                      <button
                        className={styles.secondaryButton}
                        disabled={transitionBusy}
                        onClick={() => setPendingTransition(null)}
                        type="button"
                      >
                        {t('common.cancel')}
                      </button>
                      <button
                        className={
                          pendingTransition.status === 'CANCELLED'
                            ? styles.destructiveButton
                            : styles.primaryButton
                        }
                        disabled={transitionBusy}
                        type="submit"
                      >
                        {t('careAction.transitionSubmit')}
                      </button>
                    </div>
                  </form>
                )}
              </article>
            );
          })}
        </div>
      )}

      <ConfirmationDialog
        busy={
          pendingAdoption !== null &&
          candidateBusyId === pendingAdoption.candidate.careActionCandidateId
        }
        confirmLabel={t('careAction.candidateAdoptConfirm')}
        description={
          pendingAdoption ? (
            <div className={styles.candidateAdoptFields}>
              <p>{t('careAction.candidateAdoptDescription')}</p>
              <label className={styles.field}>
                <span>{t('careAction.title')}</span>
                <input
                  maxLength={200}
                  onChange={(event) =>
                    setPendingAdoption((current) =>
                      current ? { ...current, title: event.target.value } : null,
                    )
                  }
                  required
                  value={pendingAdoption.title}
                />
              </label>
              <label className={styles.field}>
                <span>{t('careAction.dueAt')}</span>
                <input
                  min={minimumDueLocal()}
                  onChange={(event) =>
                    setPendingAdoption((current) =>
                      current ? { ...current, dueAt: event.target.value } : null,
                    )
                  }
                  required
                  type="datetime-local"
                  value={pendingAdoption.dueAt}
                />
              </label>
              <label className={styles.field}>
                <span>{t('careAction.priority')}</span>
                <select
                  onChange={(event) =>
                    setPendingAdoption((current) =>
                      current
                        ? { ...current, priority: event.target.value as CareActionPriority }
                        : null,
                    )
                  }
                  value={pendingAdoption.priority}
                >
                  {PRIORITIES.map((priority) => (
                    <option key={priority} value={priority}>
                      {t(`careActionPriority.${priority}` as MessageKey)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null
        }
        onCancel={() => setPendingAdoption(null)}
        onConfirm={() => void runAdoption()}
        open={pendingAdoption !== null}
        title={t('careAction.candidateAdoptTitle')}
      />
      <ConfirmationDialog
        busy={transitionBusy}
        confirmLabel={t('careAction.start')}
        description={t('careAction.transitionConfirmDescription')}
        onCancel={() => setConfirmStart(null)}
        onConfirm={() => {
          if (confirmStart) void runTransition(confirmStart, 'IN_PROGRESS');
        }}
        open={confirmStart !== null}
        title={t('careAction.transitionConfirmTitle')}
      />
      {toastKey && <Toast message={t(toastKey)} onDismiss={() => setToastKey(null)} />}
    </div>
  );
}
