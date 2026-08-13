import { Brain, ChatCircleDots, ShieldCheck, UsersThree } from '@phosphor-icons/react';
import type { ConsentRecord } from '@/lib/api/consent';
import styles from './ConsentSummary.module.css';

export function ConsentSummary({
  voice,
  memory,
  family,
}: {
  voice: ConsentRecord | null;
  memory: ConsentRecord | null;
  family: ConsentRecord | null;
}) {
  const items = [
    { label: '陪伴', enabled: voice !== null, icon: ChatCircleDots },
    { label: '長期記憶', enabled: memory !== null, icon: Brain },
    { label: '家屬分享', enabled: family !== null, icon: UsersThree },
  ];

  return (
    <section aria-labelledby="consent-summary-title" className={styles.summary}>
      <h2 id="consent-summary-title">
        <ShieldCheck aria-hidden="true" size={34} weight="fill" />
        您目前的選擇
      </h2>
      <dl className={styles.list}>
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label}>
              <dt>
                <Icon aria-hidden="true" size={28} />
                {item.label}
              </dt>
              <dd>{item.enabled ? '已開啟' : '未開啟'}</dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
