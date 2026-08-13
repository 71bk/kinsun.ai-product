# Stitch 前端畫面盤點與實作計畫

- 文件狀態：Analysis / Implementation Plan
- 建立日期：2026-08-13
- 適用範圍：`packages/frontend`、既有 Core API／contracts，以及工作區中的
  `stitch_kinsun.ai_eldercare_companion_system`
- 約束：本文件只描述分析、差異與建議實作順序；不代表缺少的 API、Domain、部署或外部服務已完成

## 1. 結論摘要

Stitch 可作為視覺方向，但不能直接搬入。其 HTML 使用 Tailwind CDN、raw hex、Google Fonts、
Material Symbols、Plus Jakarta Sans 與遠端圖片；現有專案則明確要求 Next.js、React、TypeScript、
CSS Modules、CSS variables、Figtree／Noto Sans TC、Phosphor Icons，且元件內不能有 raw hex。

實作時一律以 [`docs/design-system/MASTER.md`](../design-system/MASTER.md)、根目錄
[`AGENTS.md`](../../AGENTS.md) 與產品規格為準。Stitch HTML 只用來理解畫面層級、密度與元件關係，
不能成為第二套 design system 或可執行 contract。

### 1.1 可直接進入設計與前端實作

- 現有 Voice 狀態機的視覺重構。
- 單長者照護詳情、事件覆核、記憶與每日摘要的視覺重構。
- 家庭報表首頁、報表清單與報表詳情。
- Home-care assignment 的有限清單與流程。
- 長者本人 Memory Candidate 的 confirm／defer／reject 介面。
- 共用 design foundation、state、accessibility 與 regression tests。

### 1.2 必須先停住並補正式缺口

- 跨長者統計與全域覆核佇列。
- 關懷待辦。
- 通知偏好設定。
- Admin 知識來源管理。
- SOS／救護車。
- 情緒、孤獨、健康風險與異常活動推論。
- 永久語言／稱呼偏好。
- 照服員或家屬聯絡 workflow。

## 2. 目前 Route → Component → Stitch 目標畫面

### 2.1 現有 Route

| 目前 Route | 目前主要 Component | Stitch 目標 | 分類與處置 |
| --- | --- | --- | --- |
| `/`（未登入） | `PublicShell`、`Landing` | 無；Logo 僅作品牌參考 | **保留**。不讓 Stitch 的 Elder sidebar 進入 public surface。 |
| `/`（已登入長者） | `VoiceHomeClient`、`VoiceInteractionPanel`、`CompanionCharacter`、`RecordButton`、`LowConfidenceCard` | `_4` | **視覺重構**。只採中央語音狀態與陪伴角色；不採 sidebar、健康記錄、今日安排、緊急聯絡、SOS。現有九狀態與 Core Voice Gate 必須保留。 |
| `/sign-in` | Role chooser | 無 | **保留**。Auth 邊界不動。 |
| `/elder/start` | `ElderStartPage` | 無 | **保留**。Direct OIDC 入口不併入假 onboarding。 |
| `/family/join` | `FamilyJoinView` | 無 | **保留**。邀請碼與 BFF form post 不動。 |
| `/family/sign-in` | `FamilySignInView` | 無 | **保留**。 |
| `/staff/sign-in` | `StaffSignInView` | 無 | **保留**。 |
| `/auth/google/complete` | `GoogleCompleteView` | `_1` 的稱呼欄只能作局部參考 | **保留**。不可把語言與多項同意塞進身份 onboarding。 |
| `/auth/line/complete` | 共用 `GoogleCompleteView` | 無 | **合併已完成**。Google／LINE 共用 view，但 server transaction 仍分離。 |
| `/onboarding/resolve` | `ResolveOnboardingPage` | 無 | **保留**。只做角色與授權 route resolution。 |
| `/account/sign-in-methods` | `SignInMethodsClient` | 無 | **保留**。不可破壞 explicit account linking。 |
| `/line/account-link` | `LineAccountLinkClient` | 無 | **保留**。 |
| `/consent` | `ConsentPanel`、`FamilySharingConsentPanel` | `_1`、`step_2`、`step_3`、`step_4` | **功能補全＋合併**。四張 Stitch 畫面應成為同一份 Consent／資料控制流程，不建立四套狀態。目前前端只正式處理 `BASIC_VOICE` 與 `FAMILY_SHARING`。 |
| `/elder/family-access` | `ElderFamilyAccessPage` | 無 | **保留**，套用 Shared Foundation。邀請與撤銷功能已有 API。 |
| `/dashboard` | `ElderOverviewList` | `_2`；`mobile` 只作 RWD 參考 | **視覺重構**。可改成 ElderCard grid；Stitch 的總互動數、全域覆核數、待辦數目前沒有完整 aggregate API。 |
| `/dashboard/[elderId]` | `EventFilterBar`、`EventTable`、`MemoryList`、摘要 inline UI、`StateCard` | `_3`；`global_1` 的單長者 review card | **視覺重構＋合併**。今日摘要、事件、記憶、待覆核可整合為 tabs；跨長者 review queue 不能假裝由此頁提供。 |
| `/family` | `FamilyHomePage`、`StateCard` | `v2` | **視覺重構**。保留今日摘要／本週數量／重要事件，但刪除「整體狀況穩定」與類健康 check。 |
| `/family/reports` | 內嵌 `ReportCard`、`StateCard` | `family` | **視覺重構**。可加 DAILY／WEEKLY／MONTHLY tabs；必須保留 Withdrawn、Data Insufficient 與 family guard。 |
| `/privacy`、`/terms`、`/data-rights`、`/accessibility` | `LegalPage` | 無 | **保留**。只套共用 token，不改資訊架構。 |
| `/dev-speech` | `DevSpeechPage` | 無 | **保留但僅限 development**。不放入產品 navigation。 |

### 2.2 尚未存在，需要新增

| 建議 Route | Stitch 參考 | 現況 |
| --- | --- | --- |
| `/elder/memories` 或 `/elder/memory-candidates/[memoryId]` | 無，依 MASTER 設計 | **可新增**。Core 已有 list／confirm／defer／reject API；目前前端未完成長者本人確認流程。 |
| `/family/reports/[reportId]` | `family` 的「查看報表」後續頁 | **可新增**。`GET /api/v1/family/reports/{report_id}` 已存在。 |
| `/dashboard/assignments` | `mobile` 的行程部分 | **可新增有限版本**。Home-care assignment APIs 已存在，但沒有 Stitch 顯示的地址、用藥提醒、電話、完整摘要。 |
| `/dashboard/reviews` | `global_1` | **API 缺口，暫緩**。目前只有 elder-scoped care-event list，沒有跨長者 review queue。 |
| `/dashboard/tasks` | `global_2` | **Domain／API 缺口，暫緩**。目前沒有 Care Task contract。 |
| `/family/settings/notifications` | `family`／`v2` 底部 navigation | **API 缺口，暫緩**。只有 internal LINE daily job，沒有家屬偏好 CRUD。 |
| `/admin/knowledge-sources` | `admin` | **API／Auth／治理缺口，暫緩**。現有 RAG 是 staging-only retrieval 與 CLI ingestion，不是管理後台。 |

### 2.3 合併與不採用

- `_1`、`step_2`、`step_3`、`step_4`：合併進 `/consent`，不建立四個重複 route。
- `mobile`：是 `/dashboard`／`/dashboard/assignments` 的 responsive layout，不建立第二個 mobile app。
- `global_1`：其 `ReviewCard` 可用於單長者詳情；跨長者版本需等 API。
- `kinsun.ai_logo`：是品牌資產，不是頁面；需要可追溯的 SVG／透明圖來源後再放入 `public/brand/`。
- 不採用 Stitch Elder sidebar 的「健康記錄、今日安排、緊急聯絡、呼叫救護車」。
- 不採用 `global_2` 的 AI 情緒候選待辦與 `mobile` 的異常活動模式。
- 不採用 Tailwind config、Material Symbols、Google Fonts CDN、remote Stitch image URL。

## 3. 建議共用元件

| 元件 | 建議 | 來源／用途 |
| --- | --- | --- |
| `CareSidebar` | 新增 | 只用於 care/admin 桌面；小於 1024 改 top app bar。 |
| `PageHeader` | 新增 | 標題、說明、最後更新、主要 action；不可硬塞姓名或敏感資料。 |
| `SummaryMetricCard` | 新增 | 只顯示可證明的 workflow 數量；不可轉成健康指標。 |
| `ElderCard` | 從 `ElderOverviewList` 抽出 | 390→1 欄、768→2 欄、1024→3 欄；不得健康排名。 |
| `WorkflowBadge` | 沿用現有 `StateBadge` 能力 | 不另建競爭 mapping；現有 `StateCard` 已把 domain state 映為 workflow shape。 |
| `FilterChip` | 新增 | 覆核類型／狀態 filter，值仍使用 Core enum。 |
| `SearchField` | 新增 | 本地搜尋已授權清單；不能擴大 scope。 |
| `EvidenceBlock` | 新增 | 只顯示 opaque evidence ref 數量、來源版本；目前不能顯示完整逐字稿。 |
| `ReviewCard` | 從 `EventTable` 重構 | 桌機可 table、手機轉 card；VERIFY／CORRECT／REJECT／EXCLUDE 行為不變。 |
| `CareTaskCard` | 新增但封鎖 | 等正式 Care Task domain／contract 後才能接資料。 |
| `AssignmentCard` | 新增 | 只呈現 `CareAssignmentV1` 真正具有的時間、狀態與 scope。 |
| `MemoryCard` | 從 `MemoryList` 抽出 | Candidate 必須虛線；Confirmed／Active 才可實線。 |
| `ReportCard` | 從 `/family/reports` 的 local component 抽出 | 支援 Published、Withdrawn、Data Insufficient。 |
| `EmptyState` | 新增 | 沒資料時明確顯示，不用空白或虛構內容。 |
| `ErrorState` | 新增 | 非 workflow error；不得用 workflow 顏色誤導。 |
| `ConfirmationDialog` | 新增 | 撤回 Consent、刪除記憶、拒絕覆核；focus trap、返回退路、busy state。 |
| `ResponsiveTabs` | 新增 | 長者詳情與家屬報表類型。 |
| `Skeleton` | 直接重用 | 現有 Loading primitive。 |
| `LanguageSwitch`、`SignOutButton` | 直接重用 | 僅 care／family／public；voice 不顯示 UI 語言切換。 |
| Voice 元件群 | 直接重用 | `VoiceInteractionPanel`、`LowConfidenceCard`、`RecordButton` 已有安全狀態機。 |

## 4. Stitch 與 API／資料模型／contracts 落差

| 畫面 | 目前可用 | 缺口與決策 |
| --- | --- | --- |
| `_4` Voice | Voice session、ticket、ASR confirmation、companion turn 已有 client | Stitch 的健康、行程、緊急功能不存在。只重構現有 Voice 視覺。 |
| `_1`／`step_2–4` Consent | Consent list／grant／revoke 支援七個 purpose；前端正式接 BASIC／FAMILY | 永久稱呼／語言更新 API 不存在；`COMPANION_SIGNAL_ANALYSIS`、`PROACTIVE_COMPANION` 下游能力未完成。不能把 toggle 畫成可用。 |
| `_2` Care Dashboard | `/me/authorized-elders` 只有 `elder_id`、`display_name`、`care_unit_name`、`authorization_summary` | 沒有今日互動總數、全域覆核數、task count、最後互動、photo。不可把 `limit=100` 當精確總數。 |
| `_3` Elder Detail | Elder、care-events、review、memories、summaries、access-context 已存在 | Elder DTO 只有名稱、照護場域、狀態；沒有 photo、語言、中心顯示名稱、電話。 |
| `_3` 摘要覆核 | Summary list 與 `/summaries/{id}/review` 已存在 | 前端目前只 list，可補 review UI，不需改 contract。 |
| `global_1` 待覆核 | 單一 elder 的 `NEEDS_REVIEW` filter 與 review command 已存在 | 無跨長者 queue。Contract 只回 `evidence_refs`，沒有 Stitch 的完整「來源句／逐字稿」。 |
| `global_2`／`mobile` 待辦 | Home-care assignment APIs 存在 | 沒有 Care Task、情緒指標、異常偵測、用藥提醒、電話聯絡 workflow。Assignment DTO 也沒有地址或摘要。 |
| `v2` Family Home | 可由 family reports 取得 Published items、期間、更新時間 | 「整體狀況穩定」不是資料欄位，也是禁止的健康結論。Avatar/photo 不在 contract。 |
| `family` 報表中心 | list API 支援 DAILY／WEEKLY／MONTHLY／IMPORTANT_EVENT；get detail API 已存在 | 前端缺 detail route、type tabs 與通知設定。通知偏好 API 不存在。 |
| `admin` | Agent Runtime 只有 staging-only RAG retrieval；rag-ingestion 是工具鏈 | 無 source CRUD、審查 queue、同步、重試、index status、admin auth contract。不得建立假資料後台。 |
| 家屬防線 | 現有 `family-guard` 會先掃 raw payload，再濾掉非 Published／Withdrawn | 任何重構都必須保留此順序，不可先 mapping 再檢查。 |

### 4.1 不需修改 contract 就可補

- Family report detail。
- Daily summary review。
- Elder memory confirm／defer／reject。
- Home-care assignment 基本清單與 start／complete。
- Elder minimal profile 與 access context 顯示。

### 4.2 需要先提 contract／domain 缺口

- Cross-elder dashboard aggregates。
- Cross-elder review queue。
- Care Tasks。
- Notification preference CRUD。
- Knowledge source Admin。
- SOS／Emergency workflow。
- 永久語言、稱呼與聯絡資訊。
- Photo／avatar。
- 任何正式電話聯絡或家屬聯絡紀錄。

## 5. 安全與產品邊界

| 問題 | Stitch 發現 | 處置 |
| --- | --- | --- |
| 診斷／健康結論 | `v2`：「整體狀況穩定」 | **移除**。只能陳述已發布的紀錄與資料缺口。 |
| 健康紅黃綠／風險表達 | `_2`、`mobile` 使用紅色高優先卡；avatar 有綠色 check | 顏色只能代表 workflow。若無正式 priority 欄位，不能自行推導高優先。 |
| 情緒／孤獨／健康風險 | `global_2`：「近一週情緒指標有輕微波動」 | **移除整段推論**。不能以關鍵字或分數建立照護待辦。 |
| 異常偵測 | `mobile`：「系統偵測到異常活動模式」 | **移除**。目前無 contract，也違反禁止異常偵測的設計原則。 |
| 改藥／停藥／治療建議 | 未發現直接「改藥／停藥」文案；但有用藥陳述與提醒 | 保留「長者陳述」「請人工確認」即可；不得產生劑量、停藥、改藥、診斷或治療指示。 |
| 未確認資料被當事實 | `_3` 摘要與 `global_1` 可能把 AI 擷取直接呈現為正式資料 | Candidate／Needs Review 必須用虛線／覆核狀態；只有 review command 完成後才成為 Verified／Corrected。 |
| 逐字稿／證據暴露 | `global_1` 顯示「來源句（語音轉文字）」 | 現有 API 只提供 opaque evidence refs。改用 `EvidenceBlock`；不得虛構 transcript endpoint。 |
| 家屬看見內部資料 | `step_3` 宣稱分享「健康狀況」；`family` 顯示血壓／用藥 | 只有 Published report 且在 share scope 內才能顯示；Draft、Needs Review、照護筆記、逐字稿、信心值一律不得進 DOM。 |
| Consent bundled／預設開啟 | `_1` 多個 switch 看似預設開啟 | 每個 purpose 分離、預設關閉、顯示 policy version，撤回必須立即生效。 |
| 自動通知誇大 | `step_3`：「心情低落時會通知照護人員」 | 目前沒有正式 signal→review→notification workflow，改成不可用說明或移除。 |
| SOS／救護車 | `_4`、`step_2–4` 有「呼叫救護車」 | **完全不採用**。沒有 location、call provider、dispatcher acknowledgement、誤觸確認、failure/retry、audit、owner 或法規流程。 |
| Admin 能力誇大 | `admin`：「自動從來源提取知識以輔助 AI 推理」 | 必須標明 staging-only、human review 未完成；在管理 API 建立前不做可操作頁。 |

## 6. 實作順序

### 6.1 Shared Design Foundation

#### 要修改的檔案

- `packages/frontend/src/app/tokens.css`
- `packages/frontend/src/app/globals.css`
- `packages/frontend/src/components/SurfaceShell.tsx`
- `packages/frontend/src/components/SurfaceShell.module.css`
- `packages/frontend/src/components/StateCard.tsx`
- `packages/frontend/src/components/StateCard.module.css`
- `packages/frontend/src/lib/i18n/messages.ts`

#### 要新增的檔案

- `packages/frontend/src/components/layout/PageHeader.tsx`
- `packages/frontend/src/components/ui/SummaryMetricCard.tsx`
- `packages/frontend/src/components/ui/FilterChip.tsx`
- `packages/frontend/src/components/ui/SearchField.tsx`
- `packages/frontend/src/components/ui/EmptyState.tsx`
- `packages/frontend/src/components/ui/ErrorState.tsx`
- `packages/frontend/src/components/ui/ConfirmationDialog.tsx`
- 各元件對應的 `.module.css`

#### 可重用元件

`StateCard`、`StateBadge`、`Skeleton`、`LanguageSwitch`、`SignOutButton`。

#### API 依賴

無。

#### 風險

- 引入第二套 token。
- 誤搬 Stitch raw hex、8px spacing、Plus Jakarta Sans。
- 破壞不同 surface 的字級與觸控目標。

#### 驗收方式

- 只使用 CSS Modules 與 CSS variables。
- 元件內無 raw hex。
- 不引入 Tailwind。
- 200% 字級不裁切。
- Keyboard focus 與 reduced motion 可用。
- 390／768／1024／1280 無橫向捲動。

#### 測試命令

```powershell
npm run test --workspace @elderly-care/frontend
npm run lint
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
git diff --check
```

### 6.2 Care Surface

#### 要修改的檔案

- `packages/frontend/src/app/dashboard/layout.tsx`
- `packages/frontend/src/app/dashboard/page.tsx`
- `packages/frontend/src/app/dashboard/[elderId]/page.tsx`
- `packages/frontend/src/components/dashboard/ElderOverviewList.tsx`
- `packages/frontend/src/components/dashboard/EventFilterBar.tsx`
- `packages/frontend/src/components/dashboard/EventTable.tsx`
- `packages/frontend/src/components/dashboard/MemoryList.tsx`
- `packages/frontend/src/lib/api/dashboard.ts`

#### 要新增的檔案

- `packages/frontend/src/components/care/CareSidebar.tsx`
- `packages/frontend/src/components/care/ElderCard.tsx`
- `packages/frontend/src/components/care/ReviewCard.tsx`
- `packages/frontend/src/components/care/EvidenceBlock.tsx`
- `packages/frontend/src/components/care/AssignmentCard.tsx`
- `packages/frontend/src/lib/api/elders.ts`
- `packages/frontend/src/app/dashboard/assignments/page.tsx`
- `/dashboard/reviews`、`/dashboard/tasks` 僅在 API 完成後新增。

#### 可重用元件

`PageHeader`、`SummaryMetricCard`、`WorkflowBadge`、`FilterChip`、`SearchField`、`MemoryCard`。

#### API 依賴

- 已有：authorized elders、elder、access context、care events、review、memories、summaries、assignments。
- 缺少：aggregate metrics、global review queue、Care Task。

#### 風險

- N+1 查詢。
- 把 cursor page count 當 total。
- Cross-elder scope 洩漏。
- 將 confidence 當 health risk。

#### 驗收方式

- Permission Denied 不顯示 elder name／ID。
- Candidate、Needs Review、Verified 形狀清楚。
- 小於 768 時 table 轉 card，不橫向捲動。
- Review command 保持 idempotency 與 expected version。
- 不呈現 transcript。

#### 測試命令

```powershell
npm run test --workspace @elderly-care/frontend
npm run lint
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
git diff --check
```

### 6.3 Elder Surface

#### 要修改的檔案

- `packages/frontend/src/app/page.tsx`
- `packages/frontend/src/components/voice/VoiceHomeClient.tsx`
- `packages/frontend/src/components/voice/VoiceHomeClient.module.css`
- `packages/frontend/src/components/voice/VoiceInteractionPanel.tsx`
- `packages/frontend/src/app/consent/page.tsx`
- `packages/frontend/src/components/voice/ConsentPanel.tsx`
- `packages/frontend/src/components/FamilySharingConsentPanel.tsx`
- `packages/frontend/src/lib/api/consent.ts`
- `packages/frontend/src/lib/api/memories.ts`

#### 要新增的檔案

- `packages/frontend/src/components/consent/ConsentPurposeCard.tsx`
- `packages/frontend/src/components/consent/ConsentSummary.tsx`
- `packages/frontend/src/components/memory/MemoryCard.tsx`
- `packages/frontend/src/app/elder/memories/page.tsx` 或 Memory Candidate detail route。

#### 可重用元件

`ConfirmationDialog`、`EmptyState`、`ErrorState`、現有全部 Voice 元件。

#### API 依賴

- 已有：Voice Ticket、ASR confirmation、Companion Turn、Consent、memory confirm/defer/reject。
- 缺少：永久稱呼／語言偏好、proactive time settings。

#### 風險

- 多項 Consent 綁定或預設開啟。
- 宣稱未完成的 proactive／signal capability。
- 破壞 Low Confidence Gate。

#### 驗收方式

- 九個 Voice 狀態完整。
- 每個 Consent purpose 分開。
- 未實作 capability 顯示「尚未提供」而非可操作 switch。
- 撤回後不能開始新 Voice session。
- 不出現 SOS。

#### 測試命令

```powershell
npm run test --workspace @elderly-care/frontend
npm run lint
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
git diff --check
```

### 6.4 Family Surface

#### 要修改的檔案

- `packages/frontend/src/app/family/page.tsx`
- `packages/frontend/src/app/family/reports/page.tsx`
- `packages/frontend/src/app/family/layout.tsx`
- `packages/frontend/src/lib/api/family-reports.ts`
- `packages/frontend/src/lib/api/family-guard.ts`

#### 要新增的檔案

- `packages/frontend/src/components/family/FamilyNav.tsx`
- `packages/frontend/src/components/family/FamilySummaryCard.tsx`
- `packages/frontend/src/components/family/ReportCard.tsx`
- `packages/frontend/src/app/family/reports/[reportId]/page.tsx`
- 通知設定 route 暫不新增。

#### 可重用元件

`PageHeader`、`ReportCard`、`WorkflowBadge`、`EmptyState`、`ErrorState`。

#### API 依賴

- 已有：family report list/detail。
- 缺少：notification preferences、正式聯絡單位資料、家庭多長者選擇 UX。

#### 風險

- Draft exposure。
- Withdrawn content 殘留。
- 先 mapping 後 family guard。
- 以報表數量推論健康。

#### 驗收方式

- 只渲染 Published／Withdrawn。
- Withdrawn 不保留舊 items。
- Data Insufficient 有專屬狀態。
- Raw payload guard 先於 view mapping。
- 無「穩定」「改善」「風險」等結論。

#### 測試命令

```powershell
npm run test --workspace @elderly-care/frontend
npm run lint
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
git diff --check
```

### 6.5 Admin Surface

#### 要修改的檔案

現階段無；先完成 API／Auth／治理決策。

#### 通過決策後才新增

- `packages/frontend/src/app/admin/layout.tsx`
- `packages/frontend/src/app/admin/knowledge-sources/page.tsx`
- `packages/frontend/src/components/admin/KnowledgeSourceTable.tsx`
- `packages/frontend/src/components/admin/SourceReviewCard.tsx`
- `packages/frontend/src/components/admin/IngestionStatusCard.tsx`
- `packages/frontend/src/lib/api/knowledge-sources.ts`

#### 可重用元件

`CareSidebar`、`PageHeader`、`SummaryMetricCard`、`FilterChip`、`SearchField`、`WorkflowBadge`。

#### API 依賴

目前全部缺少 source CRUD、review、sync、retry、index status、admin role scope。

#### 風險

- 把 staging RAG 當 production。
- 繞過 allowlist／human review。
- 任意檔案上傳。
- Admin cross-tenant。

#### 驗收前置

- Executable contract 與 live verifier。
- Admin authorization matrix。
- Allowlist／source version／human review／receipt。
- Staging 與 production 狀態不可混稱。

未完成上述前，不應進入 UI 實作。

#### 未來測試命令

```powershell
cd services/rag-ingestion
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### 6.6 State、Accessibility 與 Regression Tests

#### 要修改的檔案

- `packages/frontend/src/components/StateCard.test.ts`
- `packages/frontend/src/components/SurfaceShell.test.ts`
- `packages/frontend/src/app/tokens.contrast.test.ts`
- `packages/frontend/src/lib/i18n/messages.test.ts`
- `packages/frontend/src/components/voice/VoiceHomeClient.test.ts`
- `packages/frontend/src/lib/api/family-guard.test.ts`
- `packages/frontend/src/lib/api/events.test.ts`
- `packages/frontend/src/lib/api/core-integration.test.ts`

#### 要新增的檔案

- 各新 shared component test。
- Dashboard、Elder Detail、Family Home、Report Detail page tests。
- `ConfirmationDialog.test.tsx`。

#### 可重用測試基礎

Vitest、現有 API client tests、dev voice preview。

#### API 依賴

Mock responses 必須符合當前 contract；不得自造不存在欄位。

#### 風險

- 只測 happy path。
- Loading 時顯示舊資料。
- Permission Denied 先渲染敏感內容。
- 英文長字串破版。

#### 驗收矩陣

- Loading／Empty／Error／Permission Denied／Data Insufficient。
- Assignment Expired／Consent Revoked／Withdrawn。
- 375／390／430／768×1024／1024×768／1280+。
- `zh-Hant`／`en`。
- Keyboard、focus trap、200% 字級。
- `prefers-reduced-motion`。
- Feature on／off。

#### 測試命令

```powershell
npm run test --workspace @elderly-care/frontend
npm run lint
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
git diff --check
git status --short
```

另做 production build 上的 Playwright 視覺檢查；目前專案尚未建立自動化 browser E2E，
因此不能把人工畫面檢查描述成 CI gate。

## 7. 實作 Gate

每個階段開始前確認：

1. 對應 Persona、User Story、Acceptance Criteria、Domain State、Security Gate 與 Test Gate。
2. 該畫面需要的資料是否真的存在於目前 executable contract。
3. 所有 read/write path 是否由 Core 重驗 actor、tenant、elder、assignment、relationship 與 Consent。
4. 是否引入新的 domain state、API、event、migration 或 provider；若是，先完成對應決策與 contract 工作。
5. 是否有 mock、staging-only、disabled flag 或尚未部署能力被誤寫成正式功能。
6. 家屬畫面是否仍在 raw payload mapping 前執行 redline guard。
7. Candidate、Needs Review、Published、Withdrawn 與 Data Insufficient 是否有不同形狀，而不只靠顏色。
8. 測試與 Demo 資料是否全部為 Synthetic／De-identified。

## 8. 本文件的證據邊界

本計畫以建立當時工作樹中的 Next.js page routes、Stitch HTML／PNG 畫面、Core OpenAPI 與相關
JSON Schemas 為依據。它不代表真實 AWS、Bedrock、OpenSearch、LINE、Email、ASR／TTS 或
production deployment 已完成驗證。正式實作時仍需重新讀取當次 code、contract、migration、
test 與環境證據。
