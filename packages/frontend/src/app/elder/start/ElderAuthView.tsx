'use client';

import {
  ArrowLeft,
  CheckCircle,
  EnvelopeSimple,
  IdentificationCard,
  LockKey,
  ShieldCheck,
} from '@phosphor-icons/react';
import Link from 'next/link';
import { type KeyboardEvent, useRef, useState } from 'react';
import { PasswordInput } from '@/components/auth/PasswordInput';
import styles from './ElderAuthView.module.css';

type AuthTab = 'login' | 'register';

interface ElderAuthViewProps {
  nativeEnabled: boolean;
  showGoogle: boolean;
  showLine: boolean;
}

const TAB_ORDER: readonly AuthTab[] = ['login', 'register'];

export function ElderAuthView({ nativeEnabled, showGoogle, showLine }: ElderAuthViewProps) {
  const [activeTab, setActiveTab] = useState<AuthTab>('login');
  const tabRefs = useRef<Record<AuthTab, HTMLButtonElement | null>>({
    login: null,
    register: null,
  });
  const hasExternalProvider = showGoogle || showLine;

  function switchTab(tab: AuthTab) {
    setActiveTab(tab);
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentTab: AuthTab) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();

    const currentIndex = TAB_ORDER.indexOf(currentTab);
    let nextTab = currentTab;
    if (event.key === 'Home') nextTab = TAB_ORDER[0];
    if (event.key === 'End') nextTab = TAB_ORDER[TAB_ORDER.length - 1];
    if (event.key === 'ArrowLeft') {
      nextTab = TAB_ORDER[(currentIndex - 1 + TAB_ORDER.length) % TAB_ORDER.length];
    }
    if (event.key === 'ArrowRight') {
      nextTab = TAB_ORDER[(currentIndex + 1) % TAB_ORDER.length];
    }

    setActiveTab(nextTab);
    tabRefs.current[nextTab]?.focus();
  }

  return (
    <div className={styles.shell} data-surface="voice">
      <header className={styles.topbar}>
        <div className={styles.topbarInner}>
          <Link className={styles.brand} href="/">
            <span className={styles.brandMark} aria-hidden="true">
              小
            </span>
            <span>
              <strong>小暖 Kinsun</strong>
              <small>長者專屬入口</small>
            </span>
          </Link>
          <Link className={styles.backLink} href="/sign-in" aria-label="返回身分選擇">
            <ArrowLeft size={26} weight="bold" aria-hidden="true" />
            <span>返回身分選擇</span>
          </Link>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.welcome} aria-labelledby="elder-welcome-title">
          <div className={styles.mascotFrame} aria-hidden="true">
            <img className={styles.mascot} src="/mascot.png" alt="" />
          </div>
          <p className={styles.eyebrow}>陪伴、同意與記憶都由您決定</p>
          <h1 id="elder-welcome-title">歡迎回來，小暖在這裡</h1>
          <p className={styles.welcomeCopy}>
            登入後可以繼續語音陪伴，也能自己確認同意設定與生活記憶。
          </p>
          <ul className={styles.assurances}>
            <li>
              <CheckCircle size={28} weight="fill" aria-hidden="true" />
              每一步都有清楚說明
            </li>
            <li>
              <ShieldCheck size={28} weight="fill" aria-hidden="true" />
              不會未經確認就留下正式記錄
            </li>
          </ul>
        </section>

        <section className={styles.authCard} aria-labelledby="elder-auth-title">
          <div className={styles.cardHeading}>
            <p className={styles.cardEyebrow}>長者帳號</p>
            <h2 id="elder-auth-title">開始使用 Kinsun</h2>
            <p>請選擇登入，或建立新的自行使用帳號。</p>
          </div>

          {nativeEnabled ? (
            <>
              <div className={styles.tabs} role="tablist" aria-label="登入或註冊">
                {TAB_ORDER.map((tab) => {
                  const selected = activeTab === tab;
                  const label = tab === 'login' ? '登入' : '註冊';
                  return (
                    <button
                      key={tab}
                      ref={(node) => {
                        tabRefs.current[tab] = node;
                      }}
                      id={`${tab}-tab`}
                      className={styles.tab}
                      type="button"
                      role="tab"
                      aria-controls={`${tab}-panel`}
                      aria-selected={selected}
                      tabIndex={selected ? 0 : -1}
                      onClick={() => switchTab(tab)}
                      onKeyDown={(event) => handleTabKeyDown(event, tab)}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>

              {activeTab === 'login' ? (
                <div
                  id="login-panel"
                  className={styles.panel}
                  role="tabpanel"
                  aria-labelledby="login-tab"
                >
                  <form action="/backend/auth/kinsun/login" method="post">
                    <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                    <div className={styles.field}>
                      <label htmlFor="loginEmail">
                        <EnvelopeSimple size={25} weight="bold" aria-hidden="true" />
                        Email
                      </label>
                      <input
                        autoComplete="email"
                        id="loginEmail"
                        maxLength={254}
                        name="email"
                        placeholder="例如：hello@example.com"
                        required
                        type="email"
                      />
                    </div>
                    <div className={styles.field}>
                      <label htmlFor="loginPassword">
                        <LockKey size={25} weight="bold" aria-hidden="true" />
                        密碼
                      </label>
                      <PasswordInput
                        autoComplete="current-password"
                        id="loginPassword"
                        maxLength={128}
                        minLength={12}
                        name="password"
                        placeholder="請輸入密碼"
                        required
                      />
                    </div>
                    <button className={styles.primaryButton} type="submit">
                      登入並開始使用
                    </button>
                  </form>

                  {hasExternalProvider && (
                    <div className={styles.providerSection}>
                      <div className={styles.divider}>
                        <span>或使用已綁定的帳號</span>
                      </div>
                      <div className={styles.providerGrid}>
                        {showGoogle && <ProviderForm provider="GOOGLE" label="使用 Google 登入" />}
                        {showLine && <ProviderForm provider="LINE" label="使用 LINE 登入" />}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div
                  id="register-panel"
                  className={styles.panel}
                  role="tabpanel"
                  aria-labelledby="register-tab"
                >
                  <p className={styles.panelIntro}>
                    先填寫 Email，我們會寄送驗證碼；驗證完成後再設定密碼。
                  </p>
                  <form action="/backend/auth/kinsun/start" method="post">
                    <input name="intent" type="hidden" value="ELDER" />
                    <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                    <div className={styles.field}>
                      <label htmlFor="displayName">
                        <IdentificationCard size={25} weight="bold" aria-hidden="true" />
                        希望我們怎麼稱呼您
                      </label>
                      <input
                        autoComplete="name"
                        id="displayName"
                        maxLength={120}
                        name="displayName"
                        placeholder="例如：王阿姨"
                      />
                      <small>這是選填欄位，之後仍可調整。</small>
                    </div>
                    <div className={styles.field}>
                      <label htmlFor="registerEmail">
                        <EnvelopeSimple size={25} weight="bold" aria-hidden="true" />
                        Email
                      </label>
                      <input
                        autoComplete="email"
                        id="registerEmail"
                        maxLength={254}
                        name="email"
                        placeholder="例如：hello@example.com"
                        required
                        type="email"
                      />
                    </div>
                    <button className={styles.primaryButton} type="submit">
                      傳送註冊驗證碼
                    </button>
                  </form>
                </div>
              )}
            </>
          ) : (
            <div className={styles.panel}>
              <p className={styles.panelIntro}>目前請使用已經綁定的登入方式繼續。</p>
              {hasExternalProvider ? (
                <div className={styles.providerGrid}>
                  {showGoogle && <ProviderForm provider="GOOGLE" label="使用 Google 登入" />}
                  {showLine && <ProviderForm provider="LINE" label="使用 LINE 登入" />}
                </div>
              ) : (
                <p className={styles.unavailable} role="status">
                  目前登入服務尚未開放，請聯絡服務單位。
                </p>
              )}
            </div>
          )}

          <aside className={styles.careCenterNotice}>
            <ShieldCheck size={28} weight="fill" aria-hidden="true" />
            <span>
              <strong>由日照中心建立資料？</strong>
              <small>不需要重複註冊，請向照護人員確認使用方式。</small>
            </span>
          </aside>
        </section>
      </main>
    </div>
  );
}

function ProviderForm({ provider, label }: { provider: 'GOOGLE' | 'LINE'; label: string }) {
  return (
    <form action="/backend/auth/login" method="post">
      <input name="intent" type="hidden" value="ELDER" />
      <input name="provider" type="hidden" value={provider} />
      <input name="returnTo" type="hidden" value="/onboarding/resolve" />
      <button className={styles.providerButton} type="submit" data-provider={provider}>
        {label}
      </button>
    </form>
  );
}
