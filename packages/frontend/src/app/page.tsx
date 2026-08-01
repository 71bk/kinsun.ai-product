'use client';

import { useEffect, useState } from 'react';
import { VoiceInteractionPanel } from '@/components/voice/VoiceInteractionPanel';
import { getRuntimeConfig } from '@/lib/runtime-config';

export default function HomePage() {
  const [config, setConfig] = useState<{ apiBaseUrl: string; wsUrl: string; token: string; elderId: string } | null>(null);
  const [consentGranted, setConsentGranted] = useState(false);

  useEffect(() => {
    setConfig(getRuntimeConfig());
    setConsentGranted(window.localStorage.getItem('elderly_care_consent_granted') === 'true');
  }, []);

  if (!config) return null;

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: 32,
        padding: 24,
      }}
    >
      <h1 style={{ fontSize: 24 }}>智慧長照 AI 陪伴系統</h1>
      <VoiceInteractionPanel wsUrl={config.wsUrl} token={config.token} consentGranted={consentGranted} />
      {!consentGranted && (
        <a href="/consent" style={{ color: '#2b6cb0', fontSize: 18 }}>
          前往同意設定
        </a>
      )}
    </main>
  );
}
