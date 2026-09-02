'use client';

import Link from 'next/link';
import { use, useCallback, useEffect, useMemo, useState } from 'react';
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

export default function ElderDetailPage({ params }: { params: Promise<{ elderId: string }> }) {
  const { elderId } = use(params);
  const { t, locale, formatDateTime } = useLocale();
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig | null>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: runtimeConfig?.apiBaseUrl ?? '/backend/core' }),
    [runtimeConfig?.apiBaseUrl],
  );
  const [workspace, setWorkspace] = useState<ElderWorkspaceView | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('events');
  const [events, setEvents] = useState<EventView[]>([]);
  const [eventFilters, setEventFilters] = useState<ListEventsFilters>({});
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
    setErrorKey(null);
    getElderWorkspace(apiConfig, elderId)
      .then((view) => {
        if (!cancelled) setWorkspace(view);
      })
      .catch((error) => {
        if (!cancelled) setErrorKey(describeError(error, 'error.loadElderFailed'));
      })
      .finally(() => {
        if (!cancelled) setWorkspaceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [apiConfig, elderId, runtimeConfig?.credentialStatus]);

  const loadEvents = useCallback(() => {
    setErrorKey(null);
    setLoading(true);
    listEvents(apiConfig, elderId, eventFilters)
      .then((response) => setEvents(response.items))
      .catch((error) => setErrorKey(describeError(error, 'error.loadEventsFailed')))
      .finally(() => setLoading(false));
  }, [apiConfig, elderId, eventFilters]);

  const loadMemories = useCallback(() => {
    setErrorKey(null);
    setLoading(true);
    listMemories(apiConfig, elderId)
      .then(setMemories)
      .catch((error) => setErrorKey(describeError(error, 'error.loadMemoriesFailed')))
      .finally(() => setLoading(false));
  }, [apiConfig, elderId]);

  const canReviewSummaries = workspace?.allowedActions.includes('summary:review') ?? false;
  const canReadCareActions = workspace?.allowedActions.includes('care_action:read') ?? false;
  const canCreateCareActions = workspace?.allowedActions.includes('care_action:create') ?? false;
  const canUpdateCareActions = workspace?.allowedActions.includes('care_action:update') ?? false;

  const loadSummaries = useCallback(() => {
    setErrorKey(null);
    setLoading(true);
    listSummaries(
      apiConfig,
      elderId,
      canReviewSummaries
        ? {
            statuses: ['DRAFT', 'READY', 'NEEDS_REVIEW', 'PUBLISHED', 'STALE', 'WITHDRAWN'],
          }
        : {},
    )
      .then((response) => setSummaries(response.items))
      .catch((error) => setErrorKey(describeError(error, 'error.loadSummariesFailed')))
      .finally(() => setLoading(false));
  }, [apiConfig, canReviewSummaries, elderId]);

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

  if (errorKey === 'error.noElderDataPermission') {
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
        {errorKey ? <ErrorState description={t(errorKey)} /> : <Skeleton rows={6} />}
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
                  setEventFilters({ status: 'NEEDS_REVIEW' });
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
          {loading ? (
            <Skeleton rows={4} />
          ) : (
            <div className={styles.summaryList}>
              <p className={styles.notice}>{t('elderDetail.summaryNotice')}</p>
              {canReviewSummaries && (
                <button
                  className={styles.primaryButton}
                  disabled={summaryBusy}
                  onClick={() => void handleGenerateSummary()}
                  type="button"
                >
                  {t('summaryReview.generateToday')}
                </button>
              )}
              {summaries.length === 0 && (
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
