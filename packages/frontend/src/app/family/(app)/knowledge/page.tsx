'use client';

import { BookOpen, CircleNotch, Info, MagnifyingGlass } from '@phosphor-icons/react';
import { useEffect, useRef, useState } from 'react';
import { apiFetch, ApiRequestError, type ApiConfig } from '@/lib/api/client';
import { askFamilyKnowledge, type FamilyKnowledgeAnswer } from '@/lib/api/family-knowledge';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig } from '@/lib/runtime-config';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import styles from './KnowledgePage.module.css';

const headings: Record<FamilyKnowledgeAnswer['status'], MessageKey> = {
  ANSWER: 'knowledge.answer',
  PARTIAL: 'knowledge.partial',
  NO_DATA: 'knowledge.noData',
  CLARIFY: 'knowledge.clarify',
  BLOCKED: 'knowledge.blocked',
  UNAVAILABLE: 'knowledge.unavailable',
};

export default function FamilyKnowledgePage() {
  const { t, locale } = useLocale();
  const [config, setConfig] = useState<ApiConfig | null>(null);
  const [access, setAccess] = useState<'loading' | 'ready' | 'denied'>('loading');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<FamilyKnowledgeAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => {
    let current = true;
    setAccess('loading');
    setAnswer(null);
    setError(false);
    setBusy(false);
    void getRuntimeConfig()
      .then(async (next) => {
        if (next.credentialStatus !== 'present') throw new Error('Authentication required');
        const profile = await apiFetch<{ role?: string; actor_type?: string }>(next, '/api/v1/me');
        if ((profile.role ?? profile.actor_type) !== 'FAMILY_MEMBER')
          throw new Error('Family only');
        if (current) {
          setConfig({ apiBaseUrl: next.apiBaseUrl });
          setAccess('ready');
        }
      })
      .catch(() => {
        if (current) setAccess('denied');
      });
    return () => {
      current = false;
      pending.current?.abort();
      pending.current = null;
    };
  }, [locale]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!config || !question.trim() || pending.current || access !== 'ready') return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setAnswer(null);
    setError(false);
    const timer = window.setTimeout(() => controller.abort(), 35000);
    try {
      const result = await askFamilyKnowledge(
        config,
        question.trim(),
        locale === 'en' ? 'en-US' : 'zh-TW',
        controller.signal,
      );
      if (pending.current === controller) setAnswer(result);
    } catch (caught) {
      if (pending.current !== controller) return;
      if (caught instanceof ApiRequestError && [401, 403, 404].includes(caught.status)) {
        setAccess('denied');
        setQuestion('');
      } else setError(true);
    } finally {
      window.clearTimeout(timer);
      if (pending.current === controller) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  if (access === 'loading') return <p role="status">{t('knowledge.loadingAccess')}</p>;
  if (access === 'denied')
    return <NotLoggedIn reason={t('knowledge.accessRequired')} linkLabel={t('common.signIn')} />;

  return (
    <main className={styles.page}>
      <PageHeader title={t('knowledge.title')} description={t('knowledge.description')} />
      <p className={styles.scope}>
        <Info size={24} aria-hidden="true" />
        {t('knowledge.scope')}
      </p>
      <form onSubmit={submit} className={styles.form}>
        <label htmlFor="knowledge-question">{t('knowledge.question')}</label>
        <textarea
          id="knowledge-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={4}
          maxLength={2000}
          required
          disabled={busy}
          aria-describedby="knowledge-privacy"
          placeholder={t('knowledge.example')}
        />
        <p id="knowledge-privacy" className={styles.hint}>
          {t('knowledge.privacy')}
        </p>
        <button className={styles.submit} type="submit" disabled={busy || !question.trim()}>
          {busy ? (
            <CircleNotch size={22} aria-hidden="true" />
          ) : (
            <MagnifyingGlass size={22} aria-hidden="true" />
          )}
          {t(busy ? 'knowledge.loading' : 'knowledge.submit')}
        </button>
      </form>
      <div aria-live="polite" aria-busy={busy}>
        {busy && <p role="status">{t('knowledge.loading')}</p>}
        {error && (
          <p role="alert" className={styles.notice}>
            {t('knowledge.serviceError')}
          </p>
        )}
        {!busy && !error && !answer && (
          <EmptyState
            title={t('knowledge.emptyTitle')}
            description={t('knowledge.emptyDescription')}
            icon={<BookOpen size={32} aria-hidden="true" />}
          />
        )}
        {answer && (
          <section className={styles.answer} aria-labelledby="knowledge-answer-heading">
            <h2 id="knowledge-answer-heading">{t(headings[answer.status])}</h2>
            <p className={styles.answerText}>{answer.answer}</p>
            {answer.sources.length > 0 && (
              <div className={styles.sources}>
                <h3>{t('knowledge.sources')}</h3>
                <ul>
                  {answer.sources.map((source, index) => (
                    <li key={`${source.url}-${index}`}>
                      <a href={source.url} target="_blank" rel="noopener noreferrer">
                        {source.title}
                      </a>
                      <p className={styles.hint}>{source.locator}</p>
                      {source.current_status === 'unknown' && (
                        <p className={styles.hint}>{t('knowledge.unknownCurrency')}</p>
                      )}
                    </li>
                  ))}
                </ul>
                <p className={styles.hint}>{t('knowledge.verify')}</p>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
