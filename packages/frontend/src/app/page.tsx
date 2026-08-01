'use client';

import { useEffect, useState } from 'react';
import { NotLoggedIn } from '@/components/NotLoggedIn';
import { DevPreviewBanner, readDevPreviewState } from '@/components/voice/dev-preview';
import { VoiceInteractionPanel } from '@/components/voice/VoiceInteractionPanel';
import type { VoicePageState } from '@/components/voice/voice-page-state';
import { AUTH_STORAGE_KEYS, getRuntimeConfig, type RuntimeConfig } from '@/lib/runtime-config';

export default function HomePage() {
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [consentGranted, setConsentGranted] = useState(false);
  const [previewState, setPreviewState] = useState<VoicePageState | null>(null);

  useEffect(() => {
    setConfig(getRuntimeConfig());
    setConsentGranted(window.localStorage.getItem(AUTH_STORAGE_KEYS.consentGranted) === 'true');
    setPreviewState(readDevPreviewState());
  }, []);

  if (!config) return null;

  // The dev preview needs no credentials: it renders the §10.1 states and issues
  // no authenticated request, opens no socket and records nothing. Auth is still
  // required for every real render, and in production readDevPreviewState()
  // always returns null so this gate is unconditional there.
  if ((!config.token || !config.elderId) && previewState === null) {
    return <NotLoggedIn reason="尚未設定登入資訊，請先完成登入設定" />;
  }

  return (
    <>
      {/* Outside <main> on purpose: this is a dev tool, not part of the voice
          surface. Inside data-surface="voice" the elder type scale (20px text,
          64px touch targets) inflates nine state links enough to push the
          mascot and the record button off screen — the very UI the banner
          exists to review. Out here it picks up the :root defaults. Normal
          flow, never position: fixed, so it cannot overlap either. */}
      {previewState !== null && <DevPreviewBanner active={previewState} />}

      {/* data-surface scopes the voice token overrides (§3). Spec puts this on
          <body>, which needs per-surface Next.js route groups — a directory
          restructure. Element-level scoping is equivalent for the cascade and is
          SSR-correct; migrate to route groups when the app topology is settled
          (design-system/MASTER.md §0 item 1). */}
      <main
        data-surface="voice"
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100dvh',
          gap: 'var(--block-gap)',
          padding: 'var(--space-6)',
          paddingBottom: 'calc(var(--space-6) + env(safe-area-inset-bottom))',
          background: 'var(--color-background)',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-xl)', color: 'var(--color-foreground)', margin: 0 }}>
          智慧長照 AI 陪伴系統
        </h1>

        <VoiceInteractionPanel
          wsUrl={config.wsUrl}
          token={config.token}
          consentGranted={consentGranted}
        />

        {!consentGranted && (
          <a
            href="/consent"
            style={{
              color: 'var(--color-primary-text)',
              fontSize: 'var(--text-base)',
              minHeight: 'var(--touch-min)',
              display: 'inline-flex',
              alignItems: 'center',
              padding: '0 var(--space-4)',
            }}
          >
            前往同意設定
          </a>
        )}
      </main>
    </>
  );
}
