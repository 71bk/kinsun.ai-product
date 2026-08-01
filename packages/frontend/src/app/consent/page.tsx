'use client';

import { useRouter } from 'next/navigation';
import { ConsentPanel } from '@/components/voice/ConsentPanel';
import { getRuntimeConfig } from '@/lib/runtime-config';

export default function ConsentPage() {
  const router = useRouter();
  const config = getRuntimeConfig();

  return (
    <main style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <ConsentPanel
        apiConfig={{ apiBaseUrl: config.apiBaseUrl, token: config.token }}
        elderId={config.elderId}
        initialGranted={false}
        onChange={(granted) => {
          window.localStorage.setItem('elderly_care_consent_granted', String(granted));
          if (granted) router.push('/');
        }}
      />
    </main>
  );
}
