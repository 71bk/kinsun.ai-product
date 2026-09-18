'use client';

import { Brain } from '@phosphor-icons/react';
import { ConsentPurposeControl } from '@/components/consent/ConsentPurposeControl';
import type { ApiConfig } from '@/lib/api/client';
import { translate } from '@/lib/i18n/messages';
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
      description="允許小暖記住您明確說出的偏好與一般生活習慣，在以後聊天時使用。"
      details={[
        ...(initialConsent && !initialConsent.scope?.personal_memory_voice_auto_save
          ? [translate('zh-Hant', 'voiceMemory.consentUpgrade')]
          : []),
        translate('zh-Hant', 'voiceMemory.consentDetails'),
        '自動保存會顯示提示，您可撤銷，或在「我的記憶」修改、刪除。同類偏好以最新陳述更新。',
        '有歧義的內容不自動保存；重要關係等候選仍需本人確認。個人自述不代表照護者已核實。',
      ]}
      grantConfirmation={translate('zh-Hant', 'voiceMemory.consentConfirm')}
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
