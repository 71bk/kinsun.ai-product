export const dynamic = 'force-dynamic';

export default function ElderStartPage() {
  const showLine = process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
  return (
    <main style={{ margin: '0 auto', maxWidth: 560, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 30, lineHeight: 1.4 }}>準備好和小暖說說話了嗎？</h1>
      <p style={{ color: '#4a5568', fontSize: 18, lineHeight: 1.7, margin: '24px 0' }}>
        首次使用請用 Google 帳號登入。完成後，我們會帶您回到這裡開始使用。
      </p>
      <form action="/backend/auth/login" method="post">
        <input name="intent" type="hidden" value="ELDER" />
        <input name="provider" type="hidden" value="GOOGLE" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <button
          style={{
            background: '#0f766e',
            border: 0,
            borderRadius: 12,
            color: 'white',
            cursor: 'pointer',
            display: 'block',
            fontSize: 22,
            padding: '18px 20px',
            width: '100%',
          }}
          type="submit"
        >
          使用 Google 繼續
        </button>
      </form>
      {showLine && (
        <form action="/backend/auth/login" method="post" style={{ marginTop: 12 }}>
          <input name="intent" type="hidden" value="ELDER" />
          <input name="provider" type="hidden" value="LINE" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <button style={{ fontSize: 18, padding: '12px 18px' }} type="submit">
            使用已連結的 LINE 登入
          </button>
        </form>
      )}
      {showLine && (
        <p style={{ color: '#4a5568', lineHeight: 1.6 }}>
          LINE 只能登入已在「登入方式」完成連結的帳號，不能建立或合併新帳號。
        </p>
      )}
      <p style={{ color: '#4a5568', lineHeight: 1.6, marginTop: 24 }}>
        需要協助嗎？請家人或照服員陪您一起完成設定。
      </p>
      <a href="/sign-in">返回選擇服務</a>
    </main>
  );
}
