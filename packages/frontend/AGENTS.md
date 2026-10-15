# AGENTS.md — frontend

本檔補充根目錄 [`AGENTS.md`](../../AGENTS.md)，只涵蓋 `packages/frontend/`；根目錄規則一律適用，
衝突時以根目錄為準。建立或改版頁面前先讀 [`docs/design-system/MASTER.md`](../../docs/design-system/MASTER.md)。

## 架構與樣式

- 唯一前端：單一 multi-role PWA，Next.js 16 App Router＋React 19＋TypeScript（ADR 0006）。不是 Vite、
  不用 Tailwind 或第二套 UI framework；樣式一律 CSS Modules＋`src/app/tokens.css`，元件內不得出現 raw hex。
- 不要建立 `apps/elder-web`／`care-web`／`family-web`；角色以 route 區分。要拆部署單元先寫 ADR 推翻 0006。
- 每個角色一個 route prefix，shell 由 route group layout 擁有：`app/elder/(app)/*`＝ElderShell、
  `app/staff/(app)/*`＝CareSidebar、`app/family/(app)/*`；sign-in 頁刻意在 group 外。
  **不要在 page 自行 import ElderShell 或手寫 `data-surface="voice"`**，否則失去 640px measure、
  64px 觸控目標與較粗 focus ring。
- 舊 URL 由 `next.config.mjs` 以 307 暫時 redirect 承接（IA 未定案前不改永久）。搬 route 時同步
  `src/lib/server/route-migration.test.ts` 與 `src/lib/server/oauth-transaction.ts` 的登入後 allowlist（搬移，不新增別名）。
- npm workspaces（根 `package.json`＋`package-lock.json`）；不要用 pnpm filter，以免搬移既有 node_modules。

## BFF 與安全

- Browser 只透過同源 BFF 呼叫後端；OAuth code exchange、access token、provider secret、session credential
  只在伺服器端，不進 client bundle、URL、log 或錯誤訊息。
- `src/app/backend/core/[...path]` 以 header allowlist 轉發、**不轉發 cookie**；新增轉發欄位先確認不夾帶憑證。
- Kinsun Email／Password：BFF 以獨立 private credential 呼叫 Core，Browser 只拿 HttpOnly Core App Session cookie；
  verification code／password 不進 response 或 log。目前寄信只有 synthetic development delivery。
- 平板交接：`/staff/elders/new` → `/elder/pair` → `/elder/session`，BFF 邊界只在 `app/backend/elder-session/*`。
  BFF 固定 acknowledgement body，不接受 client 指定 policy、actor、reason、deletion、tenant 或 elder scope；
  交換 token 時先清掉 App Session cookie，再設定獨立 Elder Session cookie。
- BFF 登入測試的 `returnTo` 必須取自 `strictRelativeReturnTo` allowlist；拒絕任意路徑不是密碼錯誤。
- 家屬端資料紅線（MASTER.md §11）前端也要擋一次，不得只依賴後端不回傳。
- 前端依驗證過的固定錯誤代碼顯示提示，不直接呈現伺服器細節。
- UI 語言切換（`src/lib/i18n/`）只改瀏覽器偏好，不得寫入任何 domain state（尤其長者語言偏好或 consent）。
  新增使用者可見字串同時補 `zh-Hant` 與 `en`（`src/lib/i18n/messages.ts`）。
- 居服工作台跨分頁更新只傳 invalidation，不傳派案或長者資料；同頁不同 BroadcastChannel instance 會收到
  自己的訊息，要用文件生命週期 source ID 排除自己。同層交班／待辦元件的 React key 要含用途前綴。

## 測試與 QA

```powershell
npm run test --workspace @elderly-care/frontend
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
npm run lint
```

- Vitest 通過不代表型別正確；新增測試後必跑 typecheck。
- Vitest lifecycle hook 用 block body 返回 void，不直接返回 `vi.unstubAllGlobals()`。
- Vitest 1 檢查 `mock.calls` 參數時用 `vi.fn<Parameters<F>, ReturnType<F>>(...)`；零參數
  `vi.fn(async () => ...)` 推論空 tuple 會讓 typecheck／build 失敗，不以型別斷言掩蓋。
- 非同步元件測試先 `await screen.findByRole(...)` 等可觀察 UI，再驗 mock 呼叫次數；呼叫已發出不代表 DOM 已更新
  （`CareActionPanel.pagination.test.ts` 曾因此偶發失敗）。Dialog 由 effect 關閉時，等 dialog 不再可見。
- 有畫面或互動改動：375／390／430 px（必要時 1440）、keyboard、loading／empty／error、
  `prefers-reduced-motion`、feature-on／off 視覺驗證。

Browser QA fixture 地雷：

- `/backend/auth/session` mock 使用實際欄位 `credential_present: true`，不是 `authenticated`（先讀 `lib/auth-session.ts`）。
- Core 成功回應需完整 meta（`correlation_id`、合法 timestamp、`schema_version="1.0"`）；錯誤回應需完整
  ErrorEnvelopeV1（`correlation_id`、`reason_code`、`retryable`、`details`）。否則只測到 malformed response。
- Skeleton 用 `role="status"`／`aria-busy="true"`，不猜 CSS Modules class。
- 跨角色合成 fixture 的照護關係除 `elder:basic:read` 還須 `elder:access_context:read`；缺 scope 只修 fixture，
  不放寬產品授權。
- 獨立埠號的 production QA server 必須設定相符的 `FRONTEND_ORIGIN`（見 [本機開發](../../docs/runbooks/local-dev.md)）。

## 常用位置

| 工作 | 位置 |
| --- | --- |
| Pages／BFF／API client | `src/app/`、`src/lib/server/`、`src/lib/api/` |
| 平板交接 | `src/app/elder/pair/`、`src/app/elder/session/`、`src/app/backend/elder-session/`、`src/lib/server/elder-session-cookie.ts` |
| Tokens／翻譯 | `src/app/tokens.css`、`src/lib/i18n/messages.ts` |
