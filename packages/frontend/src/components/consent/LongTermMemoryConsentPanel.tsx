'use client';

import { Brain } from '@phosphor-icons/react';
import { ConsentPurposeControl } from '@/components/consent/ConsentPurposeControl';
import type { ApiConfig } from '@/lib/api/client';
import {
  grantLongTermMemoryConsent,
  revokeLongTermMemoryConsent,
  type ConsentRecord,
} from '@/lib/api/consent';

export function LongTermMemoryConsentPanel({
  apiConfig,
  elderId,
  policyVersion,
  initialConsent,
  onChange,
}: {
  apiConfig: ApiConfig;
  elderId: string;
  policyVersion: string;
  initialConsent: ConsentRecord | null;
  onChange: (consent: ConsentRecord | null) => void;
}) {
  return (
    <ConsentPurposeControl
      description="允許小暖提出想記住的偏好、習慣與重要關係，但每一筆都要由您在畫面上確認。"
      details={[
        '候選內容不是事實，也不會直接成為正式記憶。',
        '只有您本人按下確認，那筆內容才會成為已確認的記憶。',
        '目前不支援用語音、照護者或家屬代替您確認。',
      ]}
      grantConfirmation="系統會記錄您同意「長期記憶」。之後每一筆想記住的內容，仍需要您另外確認。"
      grantLabel="開啟長期記憶"
      icon={<Brain size={34} weight="fill" />}
      initialConsent={initialConsent}
      onChange={onChange}
      onGrant={() => grantLongTermMemoryConsent(apiConfig, elderId, policyVersion)}
      onRevoke={(consent) => revokeLongTermMemoryConsent(apiConfig, elderId, consent.consent_id)}
      policyVersion={policyVersion}
      revokeConfirmation="撤回後，小暖不會再讀取或新增記憶。已經確認的記憶不會因此自動刪除。"
      revokeLabel="停止長期記憶"
      title="長期記憶"
    />
  );
}
