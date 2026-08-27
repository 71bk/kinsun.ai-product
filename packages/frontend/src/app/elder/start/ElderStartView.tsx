'use client';

import { Sun } from '@phosphor-icons/react';
import { useState } from 'react';
import { AuthSubmitButton } from '@/components/AuthSubmitButton';
import { AuthDivider } from '@/components/auth/AuthDivider';
import { AuthField } from '@/components/auth/AuthField';
import { ForgotPasswordHint } from '@/components/auth/ForgotPasswordHint';
import { GoogleContinueButton, LineContinueButton } from '@/components/auth/OAuthButtons';
import { TrustPoint } from '@/components/auth/TrustPoint';
import { touchLinkStyle } from '@/components/touch-link';
import styles from './ElderStartView.module.css';

type Mode = 'login' | 'register';

export function ElderStartView({
  nativeEnabled,
  showGoogle,
  showLine,
}: {
  nativeEnabled: boolean;
  showGoogle: boolean;
  showLine: boolean;
}) {
  const [mode, setMode] = useState<Mode>('login');
  const isLogin = mode === 'login';

  return (
    <div className={styles.shell} data-surface="voice">
      <a className={styles.skipLink} href="#elder-start-main">
        跳到主要內容
      </a>
      <div className={styles.grid}>
        <div className={styles.hero}>
          <span aria-hidden="true" className={styles.glow} />
          <strong className={styles.wordmark}>小暖 Kinsun</strong>
          <div>
            <span aria-hidden="true" className={styles.sunBadge}>
              <Sun size={40} weight="fill" />
            </span>
            <p className={styles.heroHeadline}>小暖陪你聊生活，也陪你安心過每一天。</p>
            <ul className={styles.heroPoints}>
              <TrustPoint tone="onDark">重要記憶，確認後才保存</TrustPoint>
              <TrustPoint tone="onDark">資料分享，由你決定</TrustPoint>
            </ul>
          </div>
        </div>

        <div className={styles.formPanel}>
          <div className={styles.formInner} id="elder-start-main" tabIndex={-1}>
            <span className={styles.eyebrow}>歡迎回來</span>
            <h1 className={styles.title}>{isLogin ? '登入 kinsun.ai' : '建立帳號'}</h1>
            <p className={styles.subtitle}>
              {isLogin ? '繼續你的陪伴與照護服務' : '完成一次 Email 驗證後設定密碼'}
            </p>

            {nativeEnabled && isLogin && (
              <form action="/backend/auth/kinsun/login" method="post" style={{ marginTop: 'var(--space-6)' }}>
                <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                <AuthField autoComplete="email" label="Email" maxLength={254} name="email" required type="email" />
                <AuthField
                  autoComplete="current-password"
                  hidePasswordLabel="隱藏密碼"
                  label="密碼 / Password"
                  labelSuffix={<ForgotPasswordHint hint="尚未開放" label="忘記密碼？" />}
                  maxLength={128}
                  minLength={12}
                  name="password"
                  required
                  showPasswordLabel="顯示密碼"
                  type="password"
                />
                <div style={{ marginTop: 'var(--space-6)' }}>
                  <AuthSubmitButton>登入 / Sign in</AuthSubmitButton>
                </div>
              </form>
            )}

            {nativeEnabled && !isLogin && (
              <form action="/backend/auth/kinsun/start" method="post" style={{ marginTop: 'var(--space-6)' }}>
                <input name="intent" type="hidden" value="ELDER" />
                <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                <AuthField label="稱呼 / Display name" name="displayName" maxLength={120} />
                <AuthField autoComplete="email" label="Email" maxLength={254} name="email" required type="email" />
                <div style={{ marginTop: 'var(--space-6)' }}>
                  <AuthSubmitButton>傳送註冊驗證碼 / Send verification code</AuthSubmitButton>
                </div>
              </form>
            )}

            {nativeEnabled && (
              <p className={styles.toggleRow}>
                {isLogin ? (
                  <>
                    還沒有帳號？{' '}
                    <button className={styles.toggleButton} onClick={() => setMode('register')} type="button">
                      建立帳號
                    </button>
                  </>
                ) : (
                  <>
                    已經有帳號？{' '}
                    <button className={styles.toggleButton} onClick={() => setMode('login')} type="button">
                      登入
                    </button>
                  </>
                )}
              </p>
            )}

            {(showGoogle || showLine) && (
              <>
                {nativeEnabled ? (
                  <AuthDivider label="或" />
                ) : (
                  <p style={{ color: 'var(--color-muted-foreground)', marginTop: 'var(--space-6)' }}>
                    已綁定第三方登入方式的帳號，也可以繼續使用：
                  </p>
                )}
                {showGoogle && (
                  <form action="/backend/auth/login" method="post" style={{ marginTop: nativeEnabled ? 0 : 'var(--space-3)' }}>
                    <input name="intent" type="hidden" value="ELDER" />
                    <input name="provider" type="hidden" value="GOOGLE" />
                    <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                    <GoogleContinueButton label="使用 Google 繼續" />
                  </form>
                )}
                {showLine && (
                  <form action="/backend/auth/login" method="post" style={{ marginTop: 'var(--space-3)' }}>
                    <input name="intent" type="hidden" value="ELDER" />
                    <input name="provider" type="hidden" value="LINE" />
                    <input name="returnTo" type="hidden" value="/onboarding/resolve" />
                    <LineContinueButton label="使用 LINE 繼續" />
                  </form>
                )}
              </>
            )}

            <p className={styles.toggleRow}>
              <a href="/sign-in" style={touchLinkStyle}>
                返回身分選擇 / Back
              </a>
            </p>

            <p className={styles.footer}>
              <a href="/privacy">隱私政策</a>
              {' · '}
              <a href="/terms">使用條款</a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
