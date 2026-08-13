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
      description="讓小暖在您主動按下按鈕後建立受控的語音或文字陪伴 Session。"
      details={[
        '不按開始就不會開啟麥克風。',
        '聽不清楚時必須由您確認，未確認內容不會送入 Agent。',
        '這項同意不等於逐字稿保存、長期記憶或照護事件建立。',
      ]}
      grantConfirmation="Core 會建立 BASIC_VOICE 同意。每次互動仍會重新檢查身分、長者範圍與同意版本。"
      grantLabel="開啟陪伴"
      icon={<ChatCircleDots size={34} weight="fill" />}
      initialConsent={initialConsent}
      onChange={onChange}
      onGrant={() => grantBasicVoiceConsent(apiConfig, elderId, policyVersion)}
      onRevoke={(consent) => revokeBasicVoiceConsent(apiConfig, elderId, consent.consent_id)}
      policyVersion={policyVersion}
      revokeConfirmation="撤回後，Core 會拒絕新的陪伴 Session，正在進行的語音 Session 也會失效。"
      revokeLabel="停止陪伴"
      title="語音與文字陪伴"
    />
  );
}
