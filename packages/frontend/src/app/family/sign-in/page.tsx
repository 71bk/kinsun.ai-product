export const dynamic = 'force-dynamic';

export default function FamilySignInPage() {
  const showLine = process.env.LINE_LOGIN_ENABLED?.trim().toLowerCase() === 'true';
  return (
    <main style={{ margin: '80px auto', maxWidth: 520, padding: 24, textAlign: 'center' }}>
      <h1 style={{ fontSize: 28 }}>家屬登入</h1>
      <p style={{ color: '#4a5568', lineHeight: 1.7, margin: '20px 0' }}>
        登入後只會顯示長者已同意分享、且仍在您授權範圍內的正式報表。
      </p>
      <form action="/backend/auth/login" method="post">
        <input name="intent" type="hidden" value="FAMILY" />
        <input name="provider" type="hidden" value="GOOGLE" />
        <input name="returnTo" type="hidden" value="/onboarding/resolve" />
        <button type="submit">使用 Google 繼續</button>
      </form>
      {showLine && (
        <form action="/backend/auth/login" method="post" style={{ marginTop: 14 }}>
          <input name="intent" type="hidden" value="FAMILY" />
          <input name="provider" type="hidden" value="LINE" />
          <input name="returnTo" type="hidden" value="/onboarding/resolve" />
          <button type="submit">使用已連結的 LINE 登入</button>
        </form>
      )}
      {showLine && <p style={{ color: '#4a5568' }}>LINE 登入不會建立或合併新帳號。</p>}
    </main>
  );
}
