'use client';

import {
  ArrowLeft,
  CheckCircle,
  ClipboardText,
  Clock,
  Prohibit,
  UserPlus,
  WarningOctagon,
} from '@phosphor-icons/react';
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { Skeleton } from '@/components/Skeleton';
import { PageHeader } from '@/components/layout/PageHeader';
import { ErrorState } from '@/components/ui/ErrorState';
import {
  ROLE_UNIT_TYPES,
  createStaffInvitation,
  invitationFailure,
  listCareUnits,
  listStaffInvitations,
  revokeStaffInvitation,
  type CareUnit,
  type IssuedStaffInvitation,
  type InvitationFailure,
  type InvitationStatus,
  type StaffInvitation,
  type StaffRole,
} from '@/lib/api/staff-invitations';
import { useLocale } from '@/lib/i18n/locale-context';
import type { MessageKey } from '@/lib/i18n/messages';
import { getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';
import styles from './AdminInvitationsPage.module.css';

const ROLES: readonly StaffRole[] = ['DAYCARE_CARE_WORKER', 'HOME_CARE_WORKER'];

const ROLE_LABEL: Record<StaffRole, MessageKey> = {
  DAYCARE_CARE_WORKER: 'admin.role.DAYCARE_CARE_WORKER',
  HOME_CARE_WORKER: 'admin.role.HOME_CARE_WORKER',
};

const STATUS_LABEL: Record<InvitationStatus, MessageKey> = {
  ISSUED: 'admin.status.ISSUED',
  ACCEPTED: 'admin.status.ACCEPTED',
  REVOKED: 'admin.status.REVOKED',
  EXPIRED: 'admin.status.EXPIRED',
};

const FAILURE_LABEL: Record<InvitationFailure, MessageKey> = {
  unavailable: 'admin.unavailable',
  conflict: 'admin.createConflict',
  network: 'admin.network',
};

/** `ISSUED` is the only status whose row is still actionable. */
function isOpen(status: InvitationStatus): boolean {
  return status === 'ISSUED';
}

export default function AdminInvitationsPage() {
  const { t, formatDateTime } = useLocale();
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [units, setUnits] = useState<CareUnit[] | null>(null);
  const [invitations, setInvitations] = useState<StaffInvitation[] | null>(null);
  const [loadFailure, setLoadFailure] = useState<InvitationFailure | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<StaffRole>('DAYCARE_CARE_WORKER');
  const [careUnitId, setCareUnitId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [createFailure, setCreateFailure] = useState<InvitationFailure | null>(null);

  const [issued, setIssued] = useState<IssuedStaffInvitation | null>(null);
  const [copied, setCopied] = useState(false);

  const [confirmingRevoke, setConfirmingRevoke] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [revokeFailure, setRevokeFailure] = useState<InvitationFailure | null>(null);

  const credentialRef = useRef<HTMLElement>(null);
  const apiConfig = useMemo(
    () => ({ apiBaseUrl: config?.apiBaseUrl ?? '/backend/core' }),
    [config?.apiBaseUrl],
  );

  const load = useCallback(async () => {
    try {
      const [unitPage, invitationPage] = await Promise.all([
        listCareUnits(apiConfig),
        listStaffInvitations(apiConfig),
      ]);
      setUnits(unitPage.items);
      setInvitations(invitationPage.items);
      setLoadFailure(null);
    } catch (error) {
      setLoadFailure(invitationFailure(error));
    }
  }, [apiConfig]);

  useEffect(() => {
    let cancelled = false;
    void getRuntimeConfig().then((runtime) => {
      if (cancelled) return;
      setConfig(runtime);
      if (runtime.credentialStatus === 'present') void load();
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  // The credential exists only in this component's state, so moving focus to it
  // is the difference between copying the link and losing the invitation.
  useEffect(() => {
    if (!issued) return;
    window.scrollTo({ behavior: 'auto', left: 0, top: 0 });
    credentialRef.current?.focus({ preventScroll: true });
  }, [issued]);

  const unitNames = useMemo(
    () => new Map((units ?? []).map((unit) => [unit.careUnitId, unit.name])),
    [units],
  );
  const selectableUnits = useMemo(
    () => (units ?? []).filter((unit) => ROLE_UNIT_TYPES[role].includes(unit.unitType)),
    [units, role],
  );

  // Switching role can strip the chosen unit out of the picker; leaving the old
  // id selected would submit a pair Core rejects with an opaque 404.
  useEffect(() => {
    if (!selectableUnits.some((unit) => unit.careUnitId === careUnitId)) {
      setCareUnitId(selectableUnits[0]?.careUnitId ?? '');
    }
  }, [selectableUnits, careUnitId]);

  if (!config) return <Skeleton rows={6} />;
  if (config.credentialStatus !== 'present') {
    return <NotLoggedIn reason={t('auth.credentialMissing')} linkLabel={t('common.signIn')} />;
  }
  if (loadFailure) {
    return (
      <main className={styles.page}>
        <ErrorState description={t(FAILURE_LABEL[loadFailure])} />
      </main>
    );
  }
  if (!invitations || !units) return <Skeleton rows={6} />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setCreateFailure(null);
    setCopied(false);
    try {
      const result = await createStaffInvitation(apiConfig, {
        email: email.trim().toLowerCase(),
        displayName: displayName.trim(),
        roleCode: role,
        careUnitId,
      });
      setIssued(result);
      setDisplayName('');
      setEmail('');
      setFormOpen(false);
    } catch (error) {
      const failure = invitationFailure(error);
      setCreateFailure(failure === 'conflict' ? 'conflict' : failure);
    } finally {
      setSubmitting(false);
    }
  }

  async function revoke(target: StaffInvitation) {
    setRevoking(target.invitationId);
    setRevokeFailure(null);
    try {
      const updated = await revokeStaffInvitation(
        apiConfig,
        target.invitationId,
        target.version,
      );
      setInvitations((current) =>
        (current ?? []).map((row) =>
          row.invitationId === updated.invitationId ? updated : row,
        ),
      );
      setConfirmingRevoke(null);
    } catch (error) {
      setRevokeFailure(invitationFailure(error));
      // The row on screen is provably out of date once the version is rejected.
      await load();
      setConfirmingRevoke(null);
    } finally {
      setRevoking(null);
    }
  }

  if (issued) {
    const link = `${window.location.origin}/join#${issued.invitationToken}`;
    return (
      <main className={styles.page}>
        <section
          aria-labelledby="credential-heading"
          className={styles.credential}
          ref={credentialRef}
          tabIndex={-1}
        >
          <p className={styles.credentialFor}>{t('admin.linkFor', { name: issued.displayName })}</p>
          <h1 className={styles.credentialTitle} id="credential-heading">
            {t('admin.linkTitle')}
          </h1>
          <p className={styles.credentialOnce}>{t('admin.linkOnce')}</p>

          <label className={styles.credentialLabel} htmlFor="invitation-link">
            {t('admin.linkLabel')}
          </label>
          <div className={styles.credentialRow}>
            <input className={styles.credentialInput} id="invitation-link" readOnly value={link} />
            <button
              className={styles.credentialCopy}
              onClick={() => {
                void navigator.clipboard.writeText(link).then(() => setCopied(true));
              }}
              type="button"
            >
              <ClipboardText aria-hidden="true" size={20} weight="fill" />
              {t('admin.linkCopy')}
            </button>
          </div>
          <p aria-live="polite" className={styles.credentialCopied}>
            {copied ? t('admin.linkCopied') : ''}
          </p>

          <dl className={styles.credentialMeta}>
            <div>
              <dt>{t('admin.role')}</dt>
              <dd>{t(ROLE_LABEL[issued.roleCode])}</dd>
            </div>
            <div>
              <dt>{t('admin.unit')}</dt>
              <dd>{unitNames.get(issued.careUnitId) ?? t('common.empty')}</dd>
            </div>
          </dl>

          <p className={styles.credentialHandover}>
            {t('admin.linkExpiry', { at: formatDateTime(issued.expiresAt) })}
            {' · '}
            {t('admin.linkHandover')}
          </p>

          <button
            className={styles.credentialDone}
            onClick={() => {
              setIssued(null);
              setCopied(false);
              void load();
            }}
            type="button"
          >
            <ArrowLeft aria-hidden="true" size={18} weight="bold" />
            {t('admin.linkDone')}
          </button>
          <p className={styles.credentialLost}>{t('admin.linkLost')}</p>
        </section>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <PageHeader
        actions={
          !formOpen && (
            <button
              className={styles.primaryButton}
              onClick={() => {
                setFormOpen(true);
                setCreateFailure(null);
              }}
              type="button"
            >
              <UserPlus aria-hidden="true" size={20} weight="fill" />
              {t('admin.issue')}
            </button>
          )
        }
        description={t('admin.subtitle')}
        title={t('admin.title')}
      />

      {formOpen && (
        <form className={styles.form} onSubmit={(event) => void submit(event)}>
          {createFailure && (
            <p className={styles.formError} role="alert">
              {t(
                createFailure === 'conflict'
                  ? 'admin.createConflict'
                  : createFailure === 'network'
                    ? 'admin.network'
                    : 'admin.createFailed',
              )}
            </p>
          )}
          <div className={styles.formGrid}>
            <label className={styles.field}>
              <span>{t('admin.name')}</span>
              <input
                autoComplete="off"
                maxLength={120}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </label>
            <label className={styles.field}>
              <span>{t('admin.email')}</span>
              <input
                autoComplete="off"
                inputMode="email"
                maxLength={254}
                onChange={(event) => setEmail(event.target.value)}
                required
                type="email"
                value={email}
              />
              <small>{t('admin.emailHint')}</small>
            </label>
            <label className={styles.field}>
              <span>{t('admin.role')}</span>
              <select
                onChange={(event) => setRole(event.target.value as StaffRole)}
                value={role}
              >
                {ROLES.map((option) => (
                  <option key={option} value={option}>
                    {t(ROLE_LABEL[option])}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>{t('admin.unit')}</span>
              <select
                disabled={selectableUnits.length === 0}
                onChange={(event) => setCareUnitId(event.target.value)}
                value={careUnitId}
              >
                {selectableUnits.map((unit) => (
                  <option key={unit.careUnitId} value={unit.careUnitId}>
                    {unit.name}
                  </option>
                ))}
              </select>
              {selectableUnits.length === 0 && <small>{t('admin.noUnit')}</small>}
            </label>
          </div>
          <div className={styles.formActions}>
            <button
              className={styles.primaryButton}
              disabled={submitting || selectableUnits.length === 0}
              type="submit"
            >
              {submitting ? t('admin.issuing') : t('admin.issue')}
            </button>
            <button
              className={styles.ghostButton}
              onClick={() => setFormOpen(false)}
              type="button"
            >
              {t('admin.cancel')}
            </button>
          </div>
        </form>
      )}

      {revokeFailure && (
        <p className={styles.listError} role="alert">
          {t(revokeFailure === 'conflict' ? 'admin.revokeConflict' : FAILURE_LABEL[revokeFailure])}
        </p>
      )}

      {invitations.length === 0 ? (
        <section className={styles.empty}>
          <p>{t('admin.empty')}</p>
          {!formOpen && (
            <button
              className={styles.primaryButton}
              onClick={() => setFormOpen(true)}
              type="button"
            >
              <UserPlus aria-hidden="true" size={20} weight="fill" />
              {t('admin.emptyAction')}
            </button>
          )}
        </section>
      ) : (
        <ul className={styles.ledger}>
          {invitations.map((row) => (
            <InvitationRow
              busy={revoking === row.invitationId}
              confirming={confirmingRevoke === row.invitationId}
              key={row.invitationId}
              onCancelRevoke={() => setConfirmingRevoke(null)}
              onConfirmRevoke={() => void revoke(row)}
              onRequestRevoke={() => {
                setRevokeFailure(null);
                setConfirmingRevoke(row.invitationId);
              }}
              row={row}
              unitName={unitNames.get(row.careUnitId) ?? null}
            />
          ))}
        </ul>
      )}
    </main>
  );
}

function InvitationRow({
  row,
  unitName,
  confirming,
  busy,
  onRequestRevoke,
  onConfirmRevoke,
  onCancelRevoke,
}: {
  row: StaffInvitation;
  unitName: string | null;
  confirming: boolean;
  busy: boolean;
  onRequestRevoke: () => void;
  onConfirmRevoke: () => void;
  onCancelRevoke: () => void;
}) {
  const { t, formatDateTime } = useLocale();
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
  }, [confirming]);

  const StatusIcon =
    row.status === 'ACCEPTED'
      ? CheckCircle
      : row.status === 'REVOKED'
        ? Prohibit
        : row.status === 'EXPIRED'
          ? WarningOctagon
          : Clock;

  return (
    <li
      className={styles.row}
      data-confirming={confirming ? 'true' : 'false'}
      data-status={row.status}
    >
      <div className={styles.rowMain}>
        <p className={styles.rowName}>{row.displayName}</p>
        <p className={styles.rowWhere}>
          {t(ROLE_LABEL[row.roleCode])}
          {unitName && <span className={styles.rowUnit}>{unitName}</span>}
        </p>
      </div>

      <p className={styles.rowStatus}>
        <StatusIcon aria-hidden="true" size={18} weight="fill" />
        <span>{t(STATUS_LABEL[row.status])}</span>
        <RowTiming row={row} />
      </p>

      <div className={styles.rowAction}>
        {confirming ? (
          <div className={styles.confirm}>
            <p className={styles.confirmQuestion}>
              {t('admin.revokeQuestion', { name: row.displayName })}
            </p>
            <p className={styles.confirmExplain}>{t('admin.revokeExplain')}</p>
            <div className={styles.confirmActions}>
              <button
                className={styles.dangerButton}
                disabled={busy}
                onClick={onConfirmRevoke}
                ref={confirmRef}
                type="button"
              >
                {busy ? t('admin.revoking') : t('admin.revokeConfirm')}
              </button>
              <button
                className={styles.ghostButton}
                disabled={busy}
                onClick={onCancelRevoke}
                type="button"
              >
                {t('admin.revokeKeep')}
              </button>
            </div>
          </div>
        ) : (
          isOpen(row.status) && (
            <button className={styles.ghostButton} onClick={onRequestRevoke} type="button">
              {t('admin.revoke')}
            </button>
          )
        )}
      </div>

      {/* Only an EXPIRED row has an honest date to show. `expires_at` is the
          only timestamp the contract exposes, and printing it under ACCEPTED or
          REVOKED would caption an activated account with "expired". */}
      {row.status === 'EXPIRED' && (
        <p className={styles.rowExpiry}>
          {t('admin.expiredOn', { at: formatDateTime(row.expiresAt) })}
        </p>
      )}
    </li>
  );
}

/**
 * "Is this still usable?" is the administrator's actual question, and a
 * timestamp 24 hours out does not answer it at a glance. Rendered only while
 * Core still reports ISSUED — Core, not this clock, decides expiry.
 */
function RowTiming({ row }: { row: StaffInvitation }) {
  const { t } = useLocale();
  if (!isOpen(row.status)) return null;
  const ms = Date.parse(row.expiresAt) - Date.now();
  if (!Number.isFinite(ms) || ms <= 0) return null;
  const minutes = Math.floor(ms / 60_000);
  return (
    <span className={styles.rowTiming}>
      {minutes < 1
        ? t('admin.expiresSoon')
        : minutes < 60
          ? t('admin.expiresInMinutes', { minutes })
          : t('admin.expiresInHours', { hours: Math.floor(minutes / 60) })}
    </span>
  );
}
