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
        '只有長者本人按下確認，Core 才能把該筆候選變成 ACTIVE。',
        '目前不支援用語音、照護者或家屬代替您確認。',
      ]}
      grantConfirmation="Core 會建立 LONG_TERM_MEMORY 同意。之後每一筆候選記憶仍需要您另外確認。"
      grantLabel="開啟長期記憶"
      icon={<Brain size={34} weight="fill" />}
      initialConsent={initialConsent}
      onChange={onChange}
      onGrant={() => grantLongTermMemoryConsent(apiConfig, elderId, policyVersion)}
      onRevoke={(consent) => revokeLongTermMemoryConsent(apiConfig, elderId, consent.consent_id)}
      policyVersion={policyVersion}
      revokeConfirmation="撤回後，Core 會拒絕新的記憶讀取與確認。這次操作不會自動要求刪除既有記憶。"
      revokeLabel="停止長期記憶"
      title="長期記憶"
    />
  );
}
