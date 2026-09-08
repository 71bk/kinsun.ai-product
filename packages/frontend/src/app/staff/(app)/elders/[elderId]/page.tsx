'use client';

import Link from 'next/link';
import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EvidenceBlock } from '@/components/care/EvidenceBlock';
import { CareActionPanel } from '@/components/care/CareActionPanel';
import { EventFilterBar } from '@/components/dashboard/EventFilterBar';
import { EventTable } from '@/components/dashboard/EventTable';
import { MemoryList } from '@/components/dashboard/MemoryList';
import { PageHeader } from '@/components/layout/PageHeader';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { StateCard, summaryState } from '@/components/StateCard';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { ErrorState } from '@/components/ui/ErrorState';
import { Toast } from '@/components/ui/Toast';
import { ApiRequestError } from '@/lib/api/client';
import { calendarDate } from '@/lib/api/daily-summary-snapshot';
import { getElderWorkspace, type ElderWorkspaceView } from '@/lib/api/elders';
import {
  listEvents,
  reviewEvent,
  summariseNeedsReview,
  type CareEventDecision,
  type EventView,
  type ListEventsFilters,
  type NeedsReviewSummary,
} from '@/lib/api/events';
import {
  deleteMemory,
  listMemories,
  rejectMemory,
  type MemoryListView,
  type MemoryView,
} from '@/lib/api/memories';
import {
  generateSummary,
  listSummaries,
  reviewSummary,
  type CoreSummaryStatus,
  type ReviewSummaryDecision,
  type SummaryView,
} from '@/lib/api/summaries';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './ElderDetailPage.module.css';

type Tab = 'events' | 'actions' | 'memories' | 'summaries';

const TAB_LABEL: Record<Tab, MessageKey> = {
  events: 'elderDetail.tabEvents',
  actions: 'elderDetail.tabActions',
  memories: 'elderDetail.tabMemories',
  summaries: 'elderDetail.tabSummaries',
};

const REVIEWABLE_SUMMARY_STATUSES = ['DRAFT', 'NEEDS_REVIEW'] as const;

function describeError(error: unknown, fallback: MessageKey): MessageKey {
  if (error instanceof ApiRequestError && (error.status === 403 || error.status === 404)) {
    return 'error.noElderDataPermission';
  }
  if (error instanceof ApiRequestError && error.status === 409) {
    return 'error.versionConflict';
  }
  return fallback;
}

export default function ElderDetailPage({ params, searchParams }: {
  params: Promise<{ elderId: string }>;
  searchParams?: Promise<{ review?: string | string[]; tab?: string | string[]; date?: string | string[] }>;
}) {
  const { elderId } = use(params);
  const query = searchParams ? use(searchParams) : {};
  const pendingReview = query.review === 'pending';
  const openSummaries = !pendingReview && query.tab === 'summaries';
  const summaryDate = openSummaries ? calendarDate(query.date) : undefined;
  return <ElderDetailWorkspace key={`${elderId}:${pendingReview}:${openSummaries}:${summaryDate}`}
    elderId={elderId} pendingReview={pendingReview} openSummaries={openSummaries} initialSummaryDate={summaryDate} />;
}

function ElderDetailWorkspace({ elderId, pendingReview, openSummaries, initialSummaryDate }: {
  elderId: string; pendingReview: boolean; openSummaries: boolean; initialSummaryDate?: string;
}) {
  const { t, locale, formatDateTime } = useLocale();
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: runtimeConfig?.apiBaseUrl ?? '/backend/core' }),
    [runtimeConfig?.apiBaseUrl],
  );
  const [workspace, setWorkspace] = useState<ElderWorkspaceView | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [workspaceError, setWorkspaceError] = useState<MessageKey | null>(null);
  const [accessRevision, setAccessRevision] = useState(0);
  const accessCheckAttempted = useRef(false);
  const [tab, setTab] = useState<Tab>(openSummaries ? 'summaries' : 'events');
  const [summaryDate, setSummaryDate] = useState(initialSummaryDate);
  const summaryRequest = useRef(0);
  const [events, setEvents] = useState<EventView[]>([]);
  const [eventFilters, setEventFilters] = useState<ListEventsFilters>(
    pendingReview ? { status: 'PENDING_REVIEW' } : {},
  );
  const [eventCursor, setEventCursor] = useState<string | null>(null);
  const [eventsLoadingMore, setEventsLoadingMore] = useState(false);
  const eventRequest = useRef(0);
  const [memories, setMemories] = useState<MemoryListView>({
    candidates: [],
    confirmed: [],
    candidateHasMore: false,
    confirmedHasMore: false,
  });
  const [summaries, setSummaries] = useState<SummaryView[]>([]);
  const [needsReview, setNeedsReview] = useState<NeedsReviewSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);
  const [pendingSummary, setPendingSummary] = useState<{
    summary: SummaryView;
    decision: ReviewSummaryDecision;
  } | null>(null);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [toastKey, setToastKey] = useState<MessageKey | null>(null);

  const recheckAccess = useCallback(() => {
    // Unmount every elder surface immediately, including child forms/dialogs.
    // Dedicated workspace error state cannot be cleared by late list responses.
    setWorkspace(null);
    setWorkspaceLoading(true);
    setWorkspaceError(null);
    setEvents([]);
    eventRequest.current += 1;
    setEventCursor(null);
    setEventsLoadingMore(false);
    setMemories({ candidates: [], confirmed: [], candidateHasMore: false, confirmedHasMore: false });
    setSummaries([]);
    summaryRequest.current += 1;
    setNeedsReview(null);
    setPendingSummary(null);
    setToastKey(null);
    // A successful workspace read followed by another denied list must not
    // create an automatic unmount/refetch loop. Explicit Retry starts a new check.
    if (accessCheckAttempted.current) {
      setWorkspaceLoading(false);
      setWorkspaceError('error.loadElderFailed');
      return;
    }
    accessCheckAttempted.current = true;
    setAccessRevision((revision) => revision + 1);
  }, []);

  useEffect(() => {
    accessCheckAttempted.current = false;
  }, [elderId, apiConfig]);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((nextConfig) => {
      if (!cancelled) setRuntimeConfig(nextConfig);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (runtimeConfig?.credentialStatus !== 'present') return;
    let cancelled = false;
    setWorkspace(null);
    setWorkspaceLoading(true);
    setWorkspaceError(null);
    setErrorKey(null);
    getElderWorkspace(apiConfig, elderId)
      .then((view) => {
        if (!cancelled) setWorkspace(view);
      })
      .catch((error) => {
        if (!cancelled) setWorkspaceError(
          error instanceof ApiRequestError && error.status === 401
            ? 'auth.credentialMissing'
            : describeError(error, 'error.loadElderFailed'),
        );
      })
      .finally(() => {
        if (!cancelled) setWorkspaceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiConfig, elderId, runtimeConfig?.credentialStatus, accessRevision]);

  const loadEvents = useCallback(() => {
    const request = ++eventRequest.current;
    setErrorKey(null);
    setLoading(true);
    setEvents([]);
    setEventCursor(null);
    setEventsLoadingMore(false);
    listEvents(apiConfig, elderId, eventFilters)
      .then((response) => {
        if (request !== eventRequest.current) return;
        setEvents(response.items);
        setEventCursor(response.nextCursor);
      })
      .catch((error) => {
        if (request !== eventRequest.current) return;
        if (error instanceof ApiRequestError && [401, 403, 404].includes(error.status)) recheckAccess();
        setErrorKey(describeError(error, 'error.loadEventsFailed'));
      })
      .finally(() => { if (request === eventRequest.current) setLoading(false); });
  }, [apiConfig, elderId, eventFilters, recheckAccess]);

  async function loadMoreEvents() {
    if (!eventCursor || loading || eventsLoadingMore) return;
    const request = eventRequest.current;
    setEventsLoadingMore(true);
    setErrorKey(null);
    try {
      const response = await listEvents(apiConfig, elderId, { ...eventFilters, cursor: eventCursor });
      if (request !== eventRequest.current) return;
      setEvents((current) => {
        const merged = new Map(current.map((event) => [event.eventId, event]));
        for (const event of response.items) {
          if (!merged.has(event.eventId) || merged.get(event.eventId)!.version <= event.version) {
            merged.set(event.eventId, event);
          }
        }
        return [...merged.values()];
      });
      setEventCursor(response.nextCursor);
    } catch (error) {
      if (request !== eventRequest.current) return;
      if (error instanceof ApiRequestError && [401, 403, 404].includes(error.status)) recheckAccess();
      setErrorKey(describeError(error, 'error.loadEventsFailed'));
    } finally {
      if (request === eventRequest.current) setEventsLoadingMore(false);
    }
  }

  const loadMemories = useCallback(() => {
    setErrorKey(null);
    setLoading(true);
    listMemories(apiConfig, elderId)
      .then(setMemories)
      .catch((error) => setErrorKey(describeError(error, 'error.loadMemoriesFailed')))
      .finally(() => setLoading(false));
  }, [apiConfig, elderId]);

  const canReviewSummaries = workspace?.allowedActions.includes('summary:review') ?? false;
  const canReadSummaries = workspace?.allowedActions.includes('summary:read') ?? false;
  const canReadCareActions = workspace?.allowedActions.includes('care_action:read') ?? false;
  const canCreateCareActions = workspace?.allowedActions.includes('care_action:create') ?? false;
  const canUpdateCareActions = workspace?.allowedActions.includes('care_action:update') ?? false;

  const loadSummaries = useCallback(() => {
    const request = ++summaryRequest.current;
    setSummaries([]);
    setErrorKey(null);
    if (!canReadSummaries) {
      setLoading(false);
      return;
    }
    setLoading(true);
    listSummaries(
      apiConfig,
      elderId,
      { ...(summaryDate ? { date: summaryDate } : {}),
        ...(canReviewSummaries ? {
          statuses: ['DRAFT', 'READY', 'NEEDS_REVIEW', 'PUBLISHED', 'STALE', 'WITHDRAWN'] as CoreSummaryStatus[],
        } : {}),
      },
    )
      .then((response) => { if (request === summaryRequest.current) setSummaries(response.items); })
      .catch((error) => {
        if (request !== summaryRequest.current) return;
        if (error instanceof ApiRequestError && [401, 403, 404].includes(error.status)) recheckAccess();
        else setErrorKey(describeError(error, 'error.loadSummariesFailed'));
      })
      .finally(() => { if (request === summaryRequest.current) setLoading(false); });
  }, [apiConfig, canReadSummaries, canReviewSummaries, elderId, recheckAccess, summaryDate]);

  const loadNeedsReview = useCallback(() => {
    summariseNeedsReview(apiConfig, elderId)
      .then(setNeedsReview)
      .catch(() => setNeedsReview(null));
  }, [apiConfig, elderId]);

  useEffect(() => {
    if (!workspace) return;
    if (tab === 'events') loadEvents();
    if (tab === 'memories') loadMemories();
    if (tab === 'summaries') loadSummaries();
    return () => { eventRequest.current += 1; summaryRequest.current += 1; };
  }, [loadEvents, loadMemories, loadSummaries, tab, workspace]);

  useEffect(() => {
    if (workspace) loadNeedsReview();
  }, [loadNeedsReview, workspace]);

  if (!runtimeConfig) return null;
  if (runtimeConfig.credentialStatus === 'unavailable') {
    return <NotLoggedIn reason={t('auth.credentialUnavailable')} linkLabel={t('common.signIn')} />;
  }
  if (runtimeConfig.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }

  async function handleReviewEvent(
    event: EventView,
    decision: CareEventDecision,
    correctedContent?: string,
  ) {
    try {
      await reviewEvent(apiConfig, elderId, event, decision, correctedContent);
      loadEvents();
      loadNeedsReview();
      setToastKey('toast.eventReviewed');
    } catch (error) {
      setErrorKey(describeError(error, 'error.reviewEventFailed'));
      throw error;
    }
  }

  async function handleRejectMemory(memory: MemoryView) {
    try {
      await rejectMemory(apiConfig, elderId, memory);
      loadMemories();
      setToastKey('toast.memoryRejected');
    } catch (error) {
      setErrorKey(describeError(error, 'error.updateMemoryFailed'));
      throw error;
    }
  }

  async function handleDeleteMemory(memory: MemoryView) {
    try {
      await deleteMemory(apiConfig, elderId, memory);
      loadMemories();
      setToastKey('toast.memoryDeleted');
    } catch (error) {
      setErrorKey(describeError(error, 'error.updateMemoryFailed'));
      throw error;
    }
  }

  async function handleSummaryReview() {
    if (!pendingSummary) return;
    setSummaryBusy(true);
    try {
      await reviewSummary(apiConfig, elderId, pendingSummary.summary, pendingSummary.decision);
      setPendingSummary(null);
      loadSummaries();
      setToastKey('toast.summaryReviewed');
    } catch (error) {
      setErrorKey(describeError(error, 'error.reviewSummaryFailed'));
    } finally {
      setSummaryBusy(false);
    }
  }

  async function handleGenerateSummary() {
    setSummaryBusy(true);
    try {
      const dateParts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Taipei',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date());
      const part = (type: 'year' | 'month' | 'day') =>
        dateParts.find((item) => item.type === type)?.value ?? '';
      const summaryDate = `${part('year')}-${part('month')}-${part('day')}`;
      await generateSummary(apiConfig, elderId, summaryDate);
      loadSummaries();
      setToastKey('toast.summaryGenerated');
    } catch (error) {
      setErrorKey(describeError(error, 'error.generateSummaryFailed'));
    } finally {
      setSummaryBusy(false);
    }
  }

  if (workspaceError === 'auth.credentialMissing') {
    return <NotLoggedIn reason={t(workspaceError)} linkLabel={t('common.signIn')} />;
  }

  if (workspaceError === 'error.noElderDataPermission' || errorKey === 'error.noElderDataPermission') {
    return (
      <main className={styles.denied}>
        <ErrorState
          action={
            <Link className={styles.backLink} href="/staff">
              {t('denied.back')}
            </Link>
          }
          description={t('error.noElderDataPermission')}
          title={t('denied.title')}
        />
      </main>
    );
  }

  if (workspaceLoading || !workspace) {
    return (
      <main className={styles.page}>
        {workspaceError ? (
          <ErrorState description={t(workspaceError)} action={
            <button type="button" className={styles.primaryButton} onClick={() => {
              accessCheckAttempted.current = false;
              recheckAccess();
            }}>
              {t('common.retry')}
            </button>
          } />
        ) : <Skeleton rows={6} />}
      </main>
    );
  }

  const listSeparator = locale === 'en' ? ', ' : '、';
  const visibleTabs: Tab[] = canReadCareActions
    ? ['events', 'actions', 'memories', 'summaries']
    : ['events', 'memories', 'summaries'];

  return (
    <main className={styles.page}>
      <PageHeader
        description={t(`careSetting.${workspace.primaryCareSetting}` as MessageKey)}
        meta={
          <span>
            {workspace.sourceSummary}
            {workspace.expiresAt
              ? ` · ${t('elderDetail.accessExpires', { at: formatDateTime(workspace.expiresAt) })}`
              : ''}
          </span>
        }
        title={workspace.displayName}
      />

      {needsReview && needsReview.count > 0 && (
        <div className={styles.reviewSummary}>
          <StateCard
            actions={
              <button
                className={styles.primaryButton}
                onClick={() => {
                  setEventFilters({ status: 'PENDING_REVIEW' });
                  setTab('events');
                }}
                type="button"
              >
                {t('needsReview.reviewNow')}
              </button>
            }
            state="needsReview"
            title={t(needsReview.atLeast ? 'needsReview.countAtLeast' : 'needsReview.count', {
              count: needsReview.count,
            })}
          >
            {t('needsReview.byConfidence', {
              low: needsReview.byConfidence.LOW,
              medium: needsReview.byConfidence.MEDIUM,
              high: needsReview.byConfidence.HIGH,
            })}
          </StateCard>
        </div>
      )}

      <div aria-label={t('elderDetail.tabsLabel')} className={styles.tabs} role="tablist">
        {visibleTabs.map((item) => (
          <button
            aria-controls={`elder-panel-${item}`}
            aria-selected={tab === item}
            className={styles.tab}
            id={`elder-tab-${item}`}
            key={item}
            onClick={() => setTab(item)}
            role="tab"
            tabIndex={tab === item ? 0 : -1}
            type="button"
          >
            {t(TAB_LABEL[item])}
          </button>
        ))}
      </div>

      {errorKey && (
        <div className={styles.error}>
          <ErrorState description={t(errorKey)} />
        </div>
      )}

      {tab === 'events' && (
        <section
          aria-labelledby="elder-tab-events"
          id="elder-panel-events"
          role="tabpanel"
          tabIndex={0}
        >
          <EventFilterBar filters={eventFilters} onChange={setEventFilters} />
          {loading ? (
            <Skeleton rows={5} />
          ) : (
            <EventTable events={events} onReview={handleReviewEvent} />
          )}
          {eventCursor && !loading && (
            <button className={styles.secondaryButton} disabled={eventsLoadingMore}
              onClick={() => void loadMoreEvents()} type="button">
              {t(eventsLoadingMore ? 'eventTable.loadingMore' : 'eventTable.loadMore')}
            </button>
          )}
        </section>
      )}

      {tab === 'actions' && canReadCareActions && (
        <section
          aria-labelledby="elder-tab-actions"
          id="elder-panel-actions"
          role="tabpanel"
          tabIndex={0}
        >
          <CareActionPanel
            apiConfig={apiConfig}
            canCreate={canCreateCareActions}
            canUpdate={canUpdateCareActions}
            elderId={elderId}
            onAccessCheck={recheckAccess}
          />
        </section>
      )}

      {tab === 'memories' && (
        <section
          aria-labelledby="elder-tab-memories"
          id="elder-panel-memories"
          role="tabpanel"
          tabIndex={0}
        >
          {loading ? (
            <Skeleton rows={4} />
          ) : (
            <MemoryList
              candidates={memories.candidates}
              confirmed={memories.confirmed}
              onDelete={handleDeleteMemory}
              onReject={handleRejectMemory}
            />
          )}
        </section>
      )}

      {tab === 'summaries' && (
        <section
          aria-labelledby="elder-tab-summaries"
          id="elder-panel-summaries"
          role="tabpanel"
          tabIndex={0}
        >
          {!canReadSummaries ? <ErrorState description={t('dashboard.summaryUnavailable')} /> : loading ? (
            <Skeleton rows={4} />
          ) : (
            <div className={styles.summaryList}>
              {summaryDate && <div>
                <p>{t('elderDetail.summaryDateFilter', { date: summaryDate })}</p>
                <button className={styles.secondaryButton} type="button" onClick={() => setSummaryDate(undefined)}>
                  {t('elderDetail.allSummaryDates')}
                </button>
              </div>}
              <p className={styles.notice}>{t('elderDetail.summaryNotice')}</p>
              {canReviewSummaries && !summaryDate && (
                <button
                  className={styles.primaryButton}
                  disabled={summaryBusy}
                  onClick={() => void handleGenerateSummary()}
                  type="button"
                >
                  {t('summaryReview.generateToday')}
                </button>
              )}
              {!errorKey && summaries.length === 0 && (
                <EmptyState
                  description={t('elderDetail.summaryEmpty')}
                  title={t('elderDetail.summaryEmptyTitle')}
                />
              )}
              {summaries.map((summary) => {
                const sourceCount = summary.items.reduce(
                  (count, item) => count + item.sourceEventIds.length,
                  0,
                );
                const reviewable =
                  canReviewSummaries &&
                  REVIEWABLE_SUMMARY_STATUSES.some((status) => status === summary.status);
                return (
                  <StateCard
                    actions={
                      reviewable ? (
                        <>
                          <button
                            className={styles.secondaryButton}
                            onClick={() => setPendingSummary({ summary, decision: 'REJECT' })}
                            type="button"
                          >
                            {t('summaryReview.reject')}
                          </button>
                          <button
                            className={styles.primaryButton}
                            onClick={() => setPendingSummary({ summary, decision: 'VERIFY' })}
                            type="button"
                          >
                            {t('summaryReview.verify')}
                          </button>
                        </>
                      ) : undefined
                    }
                    key={summary.summaryId}
                    meta={<EvidenceBlock sourceCount={sourceCount} version={summary.version} />}
                    state={summaryState(summary.status)}
                    stateLabel={t(`summaryStatus.${summary.status}` as MessageKey)}
                    title={summary.date}
                  >
                    {summary.items.length === 0 ? (
                      <p className={styles.notice}>{t('elderDetail.summaryNoItems')}</p>
                    ) : (
                      <ul className={styles.summaryItems}>
                        {summary.items.map((item, index) => (
                          <li key={`${item.category}-${index}`}>
                            <strong>{t(`summaryCategory.${item.category}` as MessageKey)}</strong>
                            <span>{item.text}</span>
                            <span className={styles.dataStatus}>
                              {t(`dataStatus.${item.dataStatus}` as MessageKey)}
                            </span>
                            <span className={styles.dataStatus}>
                              {t('summaryReview.sourceRefs', {
                                refs: item.sourceEventIds
                                  .map((sourceId) => sourceId.slice(0, 8))
                                  .join(listSeparator),
                              })}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {summary.missingFields.length > 0 && (
                      <p className={styles.notice}>
                        {t('elderDetail.dataGaps', {
                          fields: summary.missingFields.join(listSeparator),
                        })}
                      </p>
                    )}
                    {summary.conflictFlags.length > 0 && (
                      <p className={styles.notice}>
                        {t('elderDetail.conflictCount', { count: summary.conflictFlags.length })}
                      </p>
                    )}
                  </StateCard>
                );
              })}
            </div>
          )}
        </section>
      )}

      <ConfirmationDialog
        busy={summaryBusy}
        confirmLabel={
          pendingSummary?.decision === 'REJECT'
            ? t('summaryReview.reject')
            : t('summaryReview.verify')
        }
        description={t('summaryReview.confirmDescription')}
        onCancel={() => setPendingSummary(null)}
        onConfirm={() => void handleSummaryReview()}
        open={pendingSummary !== null}
        title={t('summaryReview.confirmTitle')}
        tone={pendingSummary?.decision === 'REJECT' ? 'destructive' : 'default'}
      />
      {toastKey && <Toast message={t(toastKey)} onDismiss={() => setToastKey(null)} />}
    </main>
  );
}
