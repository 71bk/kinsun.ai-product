# 家屬邀請碼加入與報表驗收（2026-09-23）

基準 main 3af4ce6（PR #59）；分支 fix/native-family-invitation-20260922。使用 production frontend 3107、本版 Core 8017、既有 Agent 8001、Supabase development DB 及真實 Gemini。所有資料均為新的合成 campaign，未攔截 browser API、未跳過 App Session 或 Core 授權。這是本機驗收，不代表外部部署驗收。

## 範圍與前置

長者由 /elder/start 註冊，透過 UI 明確開啟 BASIC_VOICE、CARE_EVENT_EXTRACTION、FAMILY_SHARING，再建立綁定 Email 的一次性邀請。家屬由 /family/join 完成 Email 驗證與密碼設定；帳號、HOUSEHOLD tenant、家屬關係均由正式 onboarding 建立，未用 SQL 預建家屬關係。Email delivery 為 development synthetic adapter，使用私存合成驗證碼；未寄送或驗證真實 Email。

只有居服員、服務單位及 IN_PROGRESS 派案由 bounded fixture 建立，供人工覆核日報；不是機構管理員派案流程驗收。新會員資格、照護與家屬關係限制四小時，未修改或延長既有帳號。密碼、驗證碼、邀請 token 與瀏覽器連線資訊只存在忽略目錄 .qa/local。

## 發現與修正

原生 Email 完成驗證後以 provider=KINSUN 呼叫共用 PendingGoogleOnboardingService，再進入 FamilyInvitationService。後者 allowlist 只有 GOOGLE／LINE，導致有效邀請的原生家屬註冊遭拒。此次納入已驗證的 KINSUN pending identity，保留原有 intent、狀態、有效期、邀請單次使用、Email 綁定、tenant、同意與分享範圍檢查。

- family_invitation_service.py：KINSUN 與現有 OIDC provider 使用相同兌換流程。
- test_family_invitation_service.py：新增 14 個 provider 成功與拒絕案例，直接執行實際 service，檢查 Actor／關係／同意／outbox，不把 redemption 整體 mock 掉。
- 長者分享頁改為驗證 Email，不再誤稱只限 Google。
- 家屬加入頁中英文對齊實際驗證流程，移除「首次加入仍須 Google」及伺服器實作細節。
- 沒有新增 schema、migration、API 欄位或擴張既有帳號權限。

9 月 22 日的部分 campaign 曾實際重現原生註冊失敗。跨日後帳號期限已到，沒有延長或復活：先退場唯一長者、撤銷三筆同意與憑證／未使用邀請，再以全新 9 月 23 日 campaign 重跑。前一批因已逾期，以限於該 campaign 的資料庫清理撤銷同意，未產生報表。

## 真實 UI 與 API 結果

| 驗證 | 結果 |
| --- | --- |
| 新長者 Email 註冊 | /me 200 ELDER |
| 本人逐項同意、建立 Email 綁定邀請 | 三筆同意；邀請 201 |
| 錯誤 Email 使用有效邀請 | 兌換失敗；/me 401，未建立 Actor，邀請仍可由正確家屬使用 |
| 正確 Email 原生家屬註冊 | /me 200 FAMILY_MEMBER，進入家屬首頁 |
| 已使用邀請由另一新帳號重放 | 拒絕；/me 401，未建立 Actor |
| 長者 UI 撤銷另一邀請，再嘗試加入 | 撤銷 200；註冊拒絕，/me 401，未建立 Actor |
| 獨立資料庫讀回 | 三個 Actor：長者、正確家屬、居服員；只有一筆 family_relationship；兩邀請 REDEEMED／REVOKED |
| 本人文字「我今天早餐吃了粥。」 | 200 SUCCESS / ALLOW，model_route=gemini-3.6-flash |
| 居服員人工驗證飲食事件 | 200 VERIFIED |
| 產生每日摘要→人工驗證 | 201 NEEDS_REVIEW → 200 READY |
| 選摘要、勾選邀請加入的家屬→建立草稿 | 201 NEEDS_REVIEW |
| 家屬讀草稿 | 404，不顯示內容 |
| 明確安全覆核後發布→家屬讀取 | 發布 200；讀取 200 PUBLISHED，顯示一筆來源及資料缺口提示 |
| 長者撤回分享，報表仍為 PUBLISHED 時重讀 | 404，原報表內容消失 |
| 居服員撤回報表、長者撤回其他同意 | 報表 WITHDRAWN；三筆同意 REVOKED |
| 退場後重用三個舊 browser sessions | /me 全部 401 |

錯誤邀請仍統一顯示「註冊服務暫時無法使用，請稍後再試」。拒絕行為正確，但提示不夠明確；本次未改動錯誤分類或揭露邀請是否存在。邀請過期、unknown provider、非 FAMILY intent、已消耗／撤銷／過期 pending identity 另以單元測試驗證，未宣稱全部經過真實 UI。

## 自動化與畫面驗證

- Core 定向 38 passed：family_invitation_service、family_invitation_tokens、pending_google_onboarding_service、kinsun_email_auth_service；修改檔案 Ruff check／format 通過。
- Frontend 登入回歸 12 passed：kinsun-auth-routes、google-auth-routes、line-auth-routes；修改檔案 ESLint 通過。
- 最終 production build 通過，包含 TypeScript。
- PR 前 CI 規則測試 26 passed（uv run --with pyyaml python -m unittest discover -s scripts/ci）。
- 語系完整性測試 12 passed，連同登入回歸共 24 個前端測試通過。
- 最終加入頁 zh-Hant 375／390／430／1440 × 900、中英文 390px 與 reduced-motion：無水平溢出，截圖已目視檢查；改正後邀請說明可讀。英語模式的既有稱呼欄位／送驗證碼按鈕仍是中文，本次未做完整介面翻譯。
- 長者分享頁同寬度 DOM 無水平溢出；已確認實際 UI 的新 Email 說明。
- 額外 Prettier 檢查指出兩個前端檔案已有格式差異；未納入無關整檔格式化，僅保留本次文案。git diff --check 通過。
- 沒有 disposable TEST_DATABASE_URL，未執行 integration conftest、schema reset 或 migration；真實 DB 驗證僅限上述新合成資料。

## 退場與證據

9 月 23 日三筆同意均由長者 UI 撤回，唯一報表由居服員 UI 撤回。腳本確認前述狀態後，將三個 Actor 設為 INACTIVE、會員資格及照護／家屬關係到期、派案取消、PasswordCredential／ExternalIdentity／AppSession 撤銷，並清理本次 pending challenges／identities。保留事件、摘要、已撤回報表及稽核；private fixture 移除密碼、驗證碼及邀請 token。

驗收瀏覽器與其私有連線檔已移除，3107／8017 QA 服務已關閉，既有開發服務保留。驗收階段未 commit／push，未寄送 Email／LINE 或部署。

本機忽略目錄證據僅存在此工作站：

- .qa/local/family-join-20260923-evidence.json
- .qa/local/family-join-20260923-retirement.json
- .qa/local/family-join-20260922-retirement.json
- .qa/local/family-join-final-*.png

## 後續

此項補上 [前次三輪文字日報驗收](cross-role-demo-acceptance-20260922.md) 尚未覆蓋的原生家屬邀請加入。Google／LINE 真實 provider 互動、實際 Email 寄送、實機語音 ASR／TTS、200% 字級、週／月報及外部通知未在本次驗證。下一個獨立驗收切片是語音環境與實機操作。本次修正另以 PR 提交，遠端 CI 結果以該 PR checks 為準；尚未部署。
