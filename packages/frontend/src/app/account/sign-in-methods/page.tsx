import { SignInMethodsClient } from '@/components/SignInMethodsClient';

const notices: Record<string, string> = {
  linked: 'LINE Login 已連結完成，Google 與 LINE 現在可登入同一個帳號。',
  already_linked: '這個 LINE Login 已經連結到目前帳號。',
  merge_required: '已找到另一個只有首次註冊資料的 LINE 帳號。請確認是否合併。',
  merged: '帳號合併完成。所有舊登入狀態已撤銷，現在使用的是新的安全 Session。',
};

const errors: Record<string, string> = {
  google_required: '請先以已連結的 Google 帳號登入，再新增 LINE Login。',
  line_link_failed: 'LINE Login 連結失敗，請重新操作。',
  manual_review_required: '兩個帳號已有正式資料，系統不會自動合併，需由管理者人工審核。',
  merge_expired: '帳號合併確認已過期，請重新驗證 LINE。',
  merge_failed: '帳號狀態已變更或合併失敗，請重新檢查後再試。',
  session_expired: '登入狀態已失效，請重新使用 Google 登入。',
};

export const dynamic = 'force-dynamic';

export default async function SignInMethodsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; status?: string }>;
}) {
  const params = await searchParams;
  const notice = params.status ? notices[params.status] : undefined;
  const error = params.error ? errors[params.error] : undefined;
  const mergeRequired = params.status === 'merge_required';

  return (
    <main style={{ margin: '0 auto', maxWidth: 620, padding: 24 }}>
      <h1 style={{ fontSize: 28 }}>登入方式</h1>
      <p style={{ color: 'var(--color-muted-foreground)', lineHeight: 1.7 }}>
        Google 與 LINE 可以連結至同一個 Core 帳號。連結時必須同時持有目前的 App Session，並重新完成
        LINE 驗證；系統不會依 Email 自動合併帳號。
      </p>
      {notice && (
        <p role="status" style={{ color: 'var(--color-accent-text)' }}>
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" style={{ color: 'var(--color-destructive)' }}>
          {error}
        </p>
      )}
      {mergeRequired && (
        <section
          style={{
            border: '1px solid var(--color-muted-foreground)',
            borderRadius: 12,
            marginBottom: 20,
            padding: 18,
          }}
        >
          <h2 style={{ fontSize: 20, marginTop: 0 }}>確認合併空白 LINE 帳號</h2>
          <p style={{ lineHeight: 1.7 }}>
            系統只會合併沒有 Consent、照護事件、報告、記憶或家庭關係的首次註冊帳號。原 LINE
            帳號會停用，LINE 登入方式會移至目前 Google 帳號，兩邊舊 Session 都會撤銷。
          </p>
          <form action="/backend/auth/identities/line/merge/confirm" method="post">
            <button
              style={{
                background: 'var(--color-accent-text)',
                border: 0,
                borderRadius: 8,
                color: 'var(--color-on-accent)',
                fontSize: 17,
                padding: '12px 16px',
              }}
              type="submit"
            >
              確認合併並登出舊 Session
            </button>
          </form>
        </section>
      )}
      <SignInMethodsClient />
      <p style={{ color: 'var(--color-muted-foreground)', lineHeight: 1.7, marginTop: 24 }}>
        LINE Login 與 LINE Bot 的 Messaging API 帳號連結屬於不同用途，憑證與識別資料不共用。
      </p>
      <a href="/">回到首頁</a>
    </main>
  );
}
