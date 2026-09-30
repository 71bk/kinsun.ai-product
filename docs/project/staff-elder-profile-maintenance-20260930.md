# 照服員維護長者資料交付紀錄

實作分支：`feat/staff-elder-profile-20260929`。2026-09-30 完成開發環境驗證。

## 使用方式

照護工作台 → 長者詳細頁 →「長者資料」。剛建立的無帳號長者，成功畫面也有資料頁連結。
照服員可修改姓名、稱呼、慣用語言，新增／更正／停用照護條目；每次填寫原因。
修改紀錄顯示操作者、時間及前後內容。停用項目保留，可切換「包含已停用資料」查看。

僅有基本與照護讀取權限者為唯讀。無其他工作區權限的建立人直接看到資料維護及協助使用入口。
其他照服員可從資料分頁進入。介面提供中英，草稿不寫入瀏覽器儲存。

## 授權與資料

- 寫入獨立 scopes：`elder:profile:update`、`care_profile:write`。讀取需要
  `elder:basic:read`；照護資料及整份修改歷史另需 `care_profile:read`。
- 僅 DAYCARE_CARE_WORKER／HOME_CARE_WORKER，逐次查驗 Actor、tenant、單位、關係／派案、
  有效時間、scope 與 ACTIVE 長者；無帳號長者另需有效 enrollment。
  家屬、長者本人、ADMIN 與跨 tenant 均不能使用此介面。不存在／未授權為 404。
- 同長者寫入鎖定 Elder，再重新授權並處理 actor-scoped idempotency。
  basic 使用 `profile_version`，照護條目沿用 `version`。舊版本回 409；重播仍檢查目前授權。
  授權 repository 使用 populate_existing，避免 SQLAlchemy identity map 沿用舊 scope。
- 每位長者最多 20 筆未停用條目；內容 500 字、原因 200 字。DISPUTED 不能直接更正，
  可停用；RETIRED 不能編輯或恢復。更正 VERIFIED 內容後回到 STAFF_RECORDED / RECORDED。
- 新增 `elder.profile_version` 及受限 `elder_profile_change` 歷史表。
  baseline audit_record 不允許敏感原文，因此歷史快照不放進一般 audit metadata。
  資料、歷史、`elder.profile_changed.v1` outbox 同交易。事件只含 IDs、變更類型與版本。
- 不改登入身份、同意、AI Memory 或家屬分享；也不自動進行醫療驗證。

## Migration 與契約

Head `e9a1b3c5d768`，前版 `d8f0a2b4c657`。先交易試跑及回滾，再 additive 套用 development；
未對共享 DB 做 reset、truncate 或 downgrade。未部署 production。

建立新長者時，建立人取得兩項寫入 scope。舊資料只回填同 tenant／單位、本人建立的有效機構收案、
無帳號 ACTIVE 長者、ACTIVE 日照 Actor／單位／會員／關係，且 scope 完整相符原始八項預設值。
自訂、縮限、失效或家屬關係不補權。Downgrade 移除本功能兩項 scope 及新增 schema，僅供
disposable 環境；共享 development 未執行 downgrade。

新增七條 API：profile GET/PATCH、care-profile GET/POST/PATCH、retire POST、profile-history GET。
清單採 opaque cursor，回應 no-store。OpenAPI 只合入本次 operations，保留既有內容；同步
strict JSON schemas、event、正反例與 exporter／static validator／runtime verifier。

## 驗證證據

- Core 全部單元測試：**1,637 passed**；新增 profile 邊界 **13 passed**。
- 前端 profile **7 passed**、中英字典 **12 passed**、既有長者頁授權回歸 **40 passed**。
  新增／調整前端檔 eslint、完整 frontend typecheck 與 production build 通過。
- 真實 Supabase SQL／HTTP rollback-only journey：CRUD、前後來源歷史、游標、冪等及鍵衝突、
  optimistic conflict、退休終態、拒絕 client actor/status、角色／tenant／scope／時間隔離、
  收案暫停、舊建立人精確回填／縮限權限不回填、20 筆上限、爭議項目更正拒絕及停用後釋出額度。
  所有 fixture 交易最後回滾。
- 靜態 contract 通過；Core runtime **113 operations** 全部已收錄，新增寫入 API 未登入為 401。
- 真實 native password → BFF cookie → Core → Supabase 的獨立合成帳號驗收：
  建立長者、姓名／語言更正、照護新增／更正／停用、歷史展開、篩選、衝突與重新載入。
  同版本並行更新回 **200／409**；同 key 並行新增回 **201／201** 且相同 entry ID。
- SQL readback：1 位無帳號長者、basic version 3、6 筆修改歷史、2 筆 RECORDED 與 1 筆 RETIRED；
  所有變更操作者皆為本次合成照服員。
- 驗收後已停用本次合成 Actor、會員及密碼。原登入畫面再次送出時，長者內容、草稿與歷史
  立即清除；沒有以失效授權完成修改。沒有變更其他測試批次或既有使用者。
- Production Playwright QA：中文 375／390／430／768／1024／1440，英文 390／768；
  修改前後展開、停用確認、衝突草稿與重新載入。DOM scrollWidth 等於 clientWidth，無橫向溢出。
  額外做 reduced-motion 與 390 寬度文字放大壓力檢查；非實體裝置或 Lighthouse 驗收。
  截圖位於 ignored `.qa/local/profile/`：`zh-*.png`、`en-*.png`、`history-en-768.png`、
  `retire-dialog-768.png`、`text-200-390.png`。已親眼檢視手機表單、平板前後內容與確認視窗。
  一項 UI 修正是 retired filter 由伺服器分頁篩選，勾選立即回饋並保留其他未儲存基本資料草稿。

真人麥克風與語音聽感依使用者要求延後，本次沒有重新啟動語音驗收。
