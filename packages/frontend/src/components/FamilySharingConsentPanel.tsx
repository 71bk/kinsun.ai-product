'use client';

import { UsersThree } from '@phosphor-icons/react';
import { ConsentPurposeControl } from '@/components/consent/ConsentPurposeControl';
import type { ApiConfig } from '@/lib/api/client';
import {
  grantFamilySharingConsent,
  revokeFamilySharingConsent,
  type ConsentRecord,
} from '@/lib/api/consent';

interface FamilySharingConsentPanelProps {
  apiConfig: ApiConfig;
  elderId: string;
  policyVersion: string;
  initialConsent: ConsentRecord | null;
  onChange: (consent: ConsentRecord | null) => void;
}

export function FamilySharingConsentPanel({
  apiConfig,
  elderId,
  policyVersion,
  initialConsent,
  onChange,
}: FamilySharingConsentPanelProps) {
  return (
    <ConsentPurposeControl
      description="允許您建立一次性邀請碼，讓指定家屬讀取正式發布的家庭報表。"
      details={[
        '邀請碼只能使用一次，預設 24 小時失效。',
        '家屬不能看到逐字稿、記憶、草稿或照護內部資料。',
        '家屬每次查看時，系統都會重新確認這項同意與家屬關係仍然有效。',
      ]}
      grantConfirmation="系統會記錄您同意「家屬分享」。分享範圍只包含每日、每週與每月的正式家屬報表。"
      grantLabel="開啟家屬分享"
      icon={<UsersThree size={34} weight="fill" />}
      initialConsent={initialConsent}
      onChange={onChange}
      onGrant={() => grantFamilySharingConsent(apiConfig, elderId, policyVersion)}
      onRevoke={(consent) => revokeFamilySharingConsent(apiConfig, elderId, consent.consent_id)}
      policyVersion={policyVersion}
      revokeConfirmation="撤回後，家屬就不能再查看報表。已經發布的資料不會因此自動刪除。"
      revokeLabel="停止家屬分享"
      title="家屬報表分享"
    />
  );
}
