'use client';

import { ChatCircleDots } from '@phosphor-icons/react';
import { ConsentPurposeControl } from '@/components/consent/ConsentPurposeControl';
import {
  grantBasicVoiceConsent,
  revokeBasicVoiceConsent,
  type ConsentApiConfig,
  type ConsentRecord,
} from '@/lib/api/consent';

export interface ConsentPanelProps {
  apiConfig: ConsentApiConfig;
  elderId: string;
  policyVersion: string;
  initialConsent: ConsentRecord | null;
  onChange: (consent: ConsentRecord | null) => void;
}

export function ConsentPanel({
  apiConfig,
  elderId,
  policyVersion,
  initialConsent,
  onChange,
}: ConsentPanelProps) {
  return (
    <ConsentPurposeControl
      description="讓小暖在您主動按下按鈕後，開始一段語音或文字陪伴。"
      details={[
        '不按開始就不會開啟麥克風。',
        '聽不清楚時必須由您確認，未確認的內容小暖不會採用。',
        '這項同意不等於逐字稿保存、長期記憶或照護事件建立。',
      ]}
      grantConfirmation="系統會記錄您同意「語音與文字陪伴」。每次互動仍會重新確認是您本人，以及這項同意仍然有效。"
      grantLabel="開啟陪伴"
      icon={<ChatCircleDots size={34} weight="fill" />}
      initialConsent={initialConsent}
      onChange={onChange}
      onGrant={() => grantBasicVoiceConsent(apiConfig, elderId, policyVersion)}
      onRevoke={(consent) => revokeBasicVoiceConsent(apiConfig, elderId, consent.consent_id)}
      policyVersion={policyVersion}
      revokeConfirmation="撤回後，小暖不會再開始新的陪伴，正在進行的語音陪伴也會立即停止。"
      revokeLabel="停止陪伴"
      title="語音與文字陪伴"
    />
  );
}
