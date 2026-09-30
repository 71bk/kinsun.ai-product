'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Skeleton } from '@/components/Skeleton';
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog';
import { ApiRequestError, createIdempotencyKey, type ApiConfig } from '@/lib/api/client';
import type { CareProfileCategory } from '@/lib/api/assisted-elders';
import {
  createCareProfile,
  getElderProfile,
  listCareProfile,
  listProfileHistory,
  retireCareProfile,
  updateCareProfile,
  updateElderProfile,
  type CareProfileEntry,
  type ElderProfile,
  type ProfileChange,
  type ProfileLanguage,
  type ProfilePage,
} from '@/lib/api/elder-profiles';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import styles from './ElderProfilePanel.module.css';

const categories: CareProfileCategory[] = [
  'HEALTH_CONDITION',
  'MEDICATION',
  'ALLERGY',
  'CARE_PRECAUTION',
];
const languages: ProfileLanguage[] = ['ZH_TW', 'NAN_TW', 'HAK_TW', 'EN_US', 'MIXED', 'UNKNOWN'];
const emptyPage = <T,>(): ProfilePage<T> => ({ items: [], next_cursor: null, has_more: false });
type BasicDraft = { name: string; preferred: string; language: ProfileLanguage; reason: string };
type Editor = {
  mode: 'create' | 'edit' | 'retire';
  entry?: CareProfileEntry;
  category: CareProfileCategory;
  content: string;
  reason: string;
};
const blankBasic: BasicDraft = { name: '', preferred: '', language: 'ZH_TW', reason: '' };

export function ElderProfilePanel({
  config,
  elderId,
  allowedActions,
  onAccessCheck,
  onNameChanged,
}: {
  config: ApiConfig;
  elderId: string;
  allowedActions: string[];
  onAccessCheck: () => void;
  onNameChanged: (name: string) => void;
}) {
  const { t, formatDateTime } = useLocale();
  const canReadCare = allowedActions.includes('care_profile:read');
  const canBasic = allowedActions.includes('elder:profile:update');
  const canCare = canReadCare && allowedActions.includes('care_profile:write');
  const [profile, setProfile] = useState<ElderProfile | null>(null);
  const [basic, setBasic] = useState<BasicDraft>(blankBasic);
  const [care, setCare] = useState<ProfilePage<CareProfileEntry>>(emptyPage);
  const [history, setHistory] = useState<ProfilePage<ProfileChange>>(emptyPage);
  const [includeRetired, setIncludeRetired] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [saved, setSaved] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [confirmRetire, setConfirmRetire] = useState(false);
  const [confirmReload, setConfirmReload] = useState(false);
  const generation = useRef(0);
  const commandBusy = useRef(false);
  const receipt = useRef<{ fingerprint: string; key: string } | null>(null);

  const fail = useCallback(
    (cause: unknown) => {
      setSaved(false);
      setConfirmRetire(false);
      if (cause instanceof ApiRequestError && [401, 403, 404].includes(cause.status)) {
        generation.current += 1;
        setProfile(null);
        setBasic(blankBasic);
        setCare(emptyPage());
        setHistory(emptyPage());
        setEditor(null);
        setConfirmRetire(false);
        setConfirmReload(false);
        receipt.current = null;
        onAccessCheck();
        return;
      }
      if (cause instanceof ApiRequestError && cause.status === 409) {
        setConflict(true);
        setError('profile.conflict');
      } else setError('profile.failed');
    },
    [onAccessCheck],
  );

  const load = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    setSaved(false);
    try {
      const [next, records, changes] = await Promise.all([
        getElderProfile(config, elderId),
        canReadCare
          ? listCareProfile(config, elderId, false)
          : Promise.resolve(emptyPage<CareProfileEntry>()),
        canReadCare
          ? listProfileHistory(config, elderId)
          : Promise.resolve(emptyPage<ProfileChange>()),
      ]);
      if (current !== generation.current) return;
      setProfile(next);
      setBasic({
        name: next.display_name,
        preferred: next.preferred_name ?? '',
        language: next.preferred_language,
        reason: '',
      });
      setCare(records);
      setHistory(changes);
      setEditor(null);
      setIncludeRetired(false);
      setConflict(false);
      receipt.current = null;
    } catch (cause) {
      if (current === generation.current) fail(cause);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [config, elderId, canReadCare, fail]);

  useEffect(() => {
    void load();
    return () => {
      generation.current += 1;
    };
  }, [load]);

  async function runCommand(fingerprint: string, command: (key: string) => Promise<void>) {
    if (commandBusy.current || conflict) return;
    commandBusy.current = true;
    setBusy(true);
    setSaved(false);
    setError(null);
    const current = generation.current;
    if (receipt.current?.fingerprint !== fingerprint)
      receipt.current = { fingerprint, key: createIdempotencyKey('elder-profile') };
    try {
      await command(receipt.current.key);
      if (current !== generation.current) return;
      receipt.current = null;
      if (canReadCare) {
        const [records, changes] = await Promise.all([
          listCareProfile(config, elderId, includeRetired),
          listProfileHistory(config, elderId),
        ]);
        if (current !== generation.current) return;
        setCare(records);
        setHistory(changes);
      }
      setSaved(true);
    } catch (cause) {
      if (current === generation.current) fail(cause);
    } finally {
      commandBusy.current = false;
      if (current === generation.current) setBusy(false);
    }
  }

  function saveBasic(event: FormEvent) {
    event.preventDefault();
    if (!profile || !canBasic) return;
    const body = {
      display_name: basic.name.trim(),
      preferred_name: basic.preferred.trim() || null,
      preferred_language: basic.language,
      reason: basic.reason.trim(),
      expected_version: profile.profile_version,
    };
    const current = generation.current;
    void runCommand(JSON.stringify(['basic', body]), async (key) => {
      const next = await updateElderProfile(config, elderId, body, key);
      if (current !== generation.current) return;
      setProfile(next);
      setBasic({
        name: next.display_name,
        preferred: next.preferred_name ?? '',
        language: next.preferred_language,
        reason: '',
      });
      onNameChanged(next.display_name);
    });
  }

  function saveCare() {
    if (!editor || !canCare) return;
    const draft = editor;
    const current = generation.current;
    const body = {
      category: draft.category,
      content: draft.content.trim(),
      reason: draft.reason.trim(),
    };
    void runCommand(
      JSON.stringify([draft.mode, draft.entry?.care_profile_entry_id, draft.entry?.version, body]),
      async (key) => {
        if (draft.mode === 'create') await createCareProfile(config, elderId, body, key);
        else if (draft.entry && draft.mode === 'edit')
          await updateCareProfile(
            config,
            elderId,
            draft.entry.care_profile_entry_id,
            { ...body, expected_version: draft.entry.version },
            key,
          );
        else if (draft.entry)
          await retireCareProfile(
            config,
            elderId,
            draft.entry.care_profile_entry_id,
            { expected_version: draft.entry.version, reason: body.reason },
            key,
          );
        if (current === generation.current) {
          setEditor(null);
          setConfirmRetire(false);
        }
      },
    );
  }

  async function more(kind: 'care' | 'history') {
    if (commandBusy.current) return;
    commandBusy.current = true;
    setBusy(true);
    const current = generation.current;
    try {
      if (kind === 'care' && care.next_cursor) {
        const next = await listCareProfile(config, elderId, includeRetired, care.next_cursor);
        if (current === generation.current)
          setCare({ ...next, items: [...care.items, ...next.items] });
      } else if (kind === 'history' && history.next_cursor) {
        const next = await listProfileHistory(config, elderId, history.next_cursor);
        if (current === generation.current)
          setHistory({ ...next, items: [...history.items, ...next.items] });
      }
    } catch (cause) {
      if (current === generation.current) fail(cause);
    } finally {
      commandBusy.current = false;
      if (current === generation.current) setBusy(false);
    }
  }

  function snapshot(value: ElderProfile | CareProfileEntry | null) {
    if (!value) return <p>{t('profile.none')}</p>;
    if ('display_name' in value)
      return (
        <>
          <p>
            {t('profile.name')}：{value.display_name}
          </p>
          <p>
            {t('profile.preferredName')}：{value.preferred_name ?? t('profile.none')}
          </p>
          <p>
            {t('profile.language')}：{t(`profile.${value.preferred_language}`)}
          </p>
        </>
      );
    return (
      <>
        <p>
          {t(`profile.${value.category}`)} · {t(`profile.${value.verification_status}`)}
        </p>
        <p className={styles.content}>{value.content}</p>
        <p>{t(`profile.${value.source_type}`)}</p>
      </>
    );
  }

  async function toggleRetired(nextValue: boolean) {
    if (commandBusy.current) return;
    commandBusy.current = true;
    setBusy(true);
    setIncludeRetired(nextValue);
    const current = generation.current;
    try {
      const next = await listCareProfile(config, elderId, nextValue);
      if (current === generation.current) {
        setCare(next);
      }
    } catch (cause) {
      if (current === generation.current) {
        setIncludeRetired(!nextValue);
        fail(cause);
      }
    } finally {
      commandBusy.current = false;
      if (current === generation.current) setBusy(false);
    }
  }

  if (loading) return <Skeleton rows={5} />;
  if (!profile)
    return (
      <div role="alert">
        <p>{t(error ?? 'profile.failed')}</p>
        <button type="button" className={styles.secondary} onClick={() => void load()}>
          {t('common.retry')}
        </button>
      </div>
    );
  const visibleCare = care.items.filter(
    (entry) => includeRetired || entry.verification_status !== 'RETIRED',
  );
  return (
    <div className={styles.panel}>
      {error && (
        <div className={styles.feedback} role="alert">
          <p>{t(error)}</p>
          {conflict && (
            <button
              className={styles.secondary}
              type="button"
              onClick={() => setConfirmReload(true)}
            >
              {t('profile.reload')}
            </button>
          )}
        </div>
      )}
      {saved && (
        <p className={styles.feedback} role="status">
          {t('profile.saved')}
        </p>
      )}
      <section className={styles.section} aria-label={t('profile.basic')}>
        <h2>{t('profile.basic')}</h2>
        {!canBasic && <p className={styles.notice}>{t('profile.readOnly')}</p>}
        <form className={styles.form} onSubmit={saveBasic}>
          <div className={styles.grid}>
            <label className={styles.field}>
              {t('profile.name')}
              <input
                value={basic.name}
                maxLength={120}
                required
                disabled={!canBasic || busy}
                onChange={(e) => setBasic({ ...basic, name: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              {t('profile.preferredName')}
              <input
                value={basic.preferred}
                maxLength={80}
                disabled={!canBasic || busy}
                onChange={(e) => setBasic({ ...basic, preferred: e.target.value })}
              />
            </label>
            <label className={styles.field}>
              {t('profile.language')}
              <select
                value={basic.language}
                disabled={!canBasic || busy}
                onChange={(e) =>
                  setBasic({ ...basic, language: e.target.value as ProfileLanguage })
                }
              >
                {languages.map((language) => (
                  <option value={language} key={language}>
                    {t(`profile.${language}`)}
                  </option>
                ))}
              </select>
            </label>
            {canBasic && (
              <label className={styles.field}>
                {t('profile.reason')}
                <input
                  value={basic.reason}
                  maxLength={200}
                  required
                  disabled={busy}
                  onChange={(e) => setBasic({ ...basic, reason: e.target.value })}
                />
              </label>
            )}
          </div>
          {canBasic && (
            <div className={styles.actions}>
              <button
                className={styles.primary}
                type="submit"
                disabled={busy || conflict || !basic.name.trim() || !basic.reason.trim()}
              >
                {t(busy ? 'profile.saving' : 'profile.save')}
              </button>
            </div>
          )}
        </form>
      </section>
      {canReadCare && (
        <>
          <section className={styles.section} aria-label={t('profile.care')}>
            <h2>{t('profile.care')}</h2>
            <p className={styles.notice}>{t('profile.notice')}</p>
            {!canCare && <p className={styles.notice}>{t('profile.readOnly')}</p>}
            <div className={styles.actions}>
              {canCare && !editor && (
                <button
                  className={styles.primary}
                  type="button"
                  disabled={busy || conflict}
                  onClick={() => {
                    setSaved(false);
                    setEditor({
                      mode: 'create',
                      category: 'CARE_PRECAUTION',
                      content: '',
                      reason: '',
                    });
                  }}
                >
                  {t('profile.add')}
                </button>
              )}
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={includeRetired}
                  disabled={busy}
                  onChange={(e) => void toggleRetired(e.target.checked)}
                />
                {t('profile.includeRetired')}
              </label>
            </div>
            {editor && (
              <form
                className={styles.entry}
                aria-label={t(
                  editor.mode === 'create'
                    ? 'profile.add'
                    : editor.mode === 'edit'
                      ? 'profile.edit'
                      : 'profile.retire',
                )}
                onSubmit={(event) => {
                  event.preventDefault();
                  if (editor.mode === 'retire') setConfirmRetire(true);
                  else saveCare();
                }}
              >
                <label className={styles.field}>
                  {t('profile.category')}
                  <select
                    disabled={busy || editor.mode === 'retire'}
                    value={editor.category}
                    onChange={(e) =>
                      setEditor({ ...editor, category: e.target.value as CareProfileCategory })
                    }
                  >
                    {categories.map((category) => (
                      <option key={category} value={category}>
                        {t(`profile.${category}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={styles.field}>
                  {t('profile.content')}
                  <textarea
                    required
                    maxLength={500}
                    disabled={busy || editor.mode === 'retire'}
                    value={editor.content}
                    onChange={(e) => setEditor({ ...editor, content: e.target.value })}
                  />
                </label>
                <label className={styles.field}>
                  {t('profile.reason')}
                  <input
                    required
                    maxLength={200}
                    disabled={busy}
                    value={editor.reason}
                    onChange={(e) => setEditor({ ...editor, reason: e.target.value })}
                  />
                </label>
                <div className={styles.actions}>
                  <button
                    type="submit"
                    className={styles.primary}
                    disabled={busy || conflict || !editor.content.trim() || !editor.reason.trim()}
                  >
                    {t(editor.mode === 'retire' ? 'profile.retire' : 'profile.save')}
                  </button>
                  <button
                    type="button"
                    className={styles.secondary}
                    disabled={busy}
                    onClick={() => setEditor(null)}
                  >
                    {t('profile.cancel')}
                  </button>
                </div>
              </form>
            )}
            {visibleCare.length === 0 && <p>{t('profile.empty')}</p>}
            <div className={styles.list}>
              {visibleCare.map((entry) => (
                <article key={entry.care_profile_entry_id} className={styles.entry}>
                  <h3>{t(`profile.${entry.category}`)}</h3>
                  <p className={styles.meta}>
                    {t(`profile.${entry.verification_status}`)} ·{' '}
                    {t(`profile.${entry.source_type}`)} ·{' '}
                    {t('profile.version', { version: entry.version })}
                  </p>
                  <p className={styles.content}>{entry.content}</p>
                  <p className={styles.meta}>
                    {t('profile.effective', { time: formatDateTime(entry.effective_from) })}
                  </p>
                  {entry.retired_at && (
                    <p className={styles.meta}>
                      {t('profile.retiredAt', { time: formatDateTime(entry.retired_at) })}
                    </p>
                  )}
                  {canCare && entry.verification_status !== 'RETIRED' && (
                    <div className={styles.actions}>
                      {entry.verification_status !== 'DISPUTED' && (
                        <button
                          className={styles.secondary}
                          type="button"
                          disabled={busy || !!editor || conflict}
                          onClick={() =>
                            setEditor({
                              mode: 'edit',
                              entry,
                              category: entry.category,
                              content: entry.content,
                              reason: '',
                            })
                          }
                        >
                          {t('profile.edit')}
                        </button>
                      )}
                      <button
                        className={styles.secondary}
                        type="button"
                        disabled={busy || !!editor || conflict}
                        onClick={() =>
                          setEditor({
                            mode: 'retire',
                            entry,
                            category: entry.category,
                            content: entry.content,
                            reason: '',
                          })
                        }
                      >
                        {t('profile.retire')}
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
            {care.has_more && (
              <button
                className={styles.secondary}
                type="button"
                disabled={busy}
                onClick={() => void more('care')}
              >
                {t('profile.more')}
              </button>
            )}
          </section>
          <section className={styles.section} aria-label={t('profile.history')}>
            <h2>{t('profile.history')}</h2>
            <p className={styles.notice}>{t('profile.historyNotice')}</p>
            {history.items.length === 0 && <p>{t('profile.noHistory')}</p>}
            {history.items.map((change) => (
              <article className={styles.entry} key={change.profile_change_id}>
                <h3>{t(`profile.${change.change_type}`)}</h3>
                <p className={styles.meta}>
                  {t('profile.authorTime', {
                    name: change.changed_by_name,
                    time: formatDateTime(change.created_at),
                  })}
                </p>
                <p>
                  {t('profile.reason')}：{change.reason}
                </p>
                <details className={styles.history}>
                  <summary>{t('profile.details')}</summary>
                  <div className={styles.snapshots}>
                    <div>
                      <h4>{t('profile.before')}</h4>
                      {snapshot(change.before_data)}
                    </div>
                    <div>
                      <h4>{t('profile.after')}</h4>
                      {snapshot(change.after_data)}
                    </div>
                  </div>
                </details>
              </article>
            ))}
            {history.has_more && (
              <button
                className={styles.secondary}
                type="button"
                disabled={busy}
                onClick={() => void more('history')}
              >
                {t('profile.more')}
              </button>
            )}
          </section>
        </>
      )}
      <ConfirmationDialog
        open={confirmRetire}
        busy={busy}
        title={t('profile.retireTitle')}
        description={t('profile.retireDescription')}
        confirmLabel={t('profile.retire')}
        onConfirm={saveCare}
        onCancel={() => setConfirmRetire(false)}
      />
      <ConfirmationDialog
        open={confirmReload}
        title={t('profile.reloadTitle')}
        description={t('profile.reloadDescription')}
        confirmLabel={t('profile.reload')}
        onConfirm={() => {
          setConfirmReload(false);
          void load();
        }}
        onCancel={() => setConfirmReload(false)}
      />
    </div>
  );
}
