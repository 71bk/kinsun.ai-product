'use client';

import { ClipboardText } from '@phosphor-icons/react';
import { ConsentPurposeControl } from '@/components/consent/ConsentPurposeControl';
import type { ApiConfig } from '@/lib/api/client';
import {
  grantCareEventExtractionConsent,
  revokeCareEventExtractionConsent,
  type ConsentRecord,
} from '@/lib/api/consent';
import { translate } from '@/lib/i18n/messages';

export function CareEventExtractionConsentPanel({
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
      description={translate('zh-Hant', 'careEventConsent.description')}
      details={[
        translate('zh-Hant', 'careEventConsent.review'),
        translate('zh-Hant', 'careEventConsent.separate'),
        translate('zh-Hant', 'careEventConsent.stop'),
      ]}
      grantConfirmation={translate('zh-Hant', 'careEventConsent.grantConfirm')}
      grantLabel={translate('zh-Hant', 'careEventConsent.grant')}
      icon={<ClipboardText size={34} weight="fill" />}
      initialConsent={initialConsent}
      onChange={onChange}
      onGrant={() => grantCareEventExtractionConsent(apiConfig, elderId, policyVersion)}
      onRevoke={(consent) => revokeCareEventExtractionConsent(apiConfig, elderId, consent.consent_id)}
      policyVersion={policyVersion}
      revokeConfirmation={translate('zh-Hant', 'careEventConsent.revokeConfirm')}
      revokeLabel={translate('zh-Hant', 'careEventConsent.revoke')}
      title={translate('zh-Hant', 'careEventConsent.title')}
    />
  );
}
