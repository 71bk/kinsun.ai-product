# 照服員收案管理交付紀錄

日期：2026-09-30。分支：`feat/staff-enrollment-lifecycle-20260930`。
範圍：既有無帳號機構長者，由原收案建立人管理服務狀態；不是代建 Email／密碼帳號。

## 使用行為

照護工作台新增「收案管理」入口，亦可直接進入 `/staff/enrollments`。
原建立人可查看自己的收案、填寫原因、確認影響後暫停／恢復／結案，並查看操作人、時間與歷史。

- 服務中 → 暫停；暫停 → 恢復；服務中／暫停 → 結案。結案為終態。
- 暫停／結案同一交易結束現有平板授權、未完成對話與未完成派案；一般機構照護存取及清單拒絕該長者。
- 恢復後重新配對平板，已取消派案需重新安排；不恢復獨立撤銷的 scope。
- 保留長者與照護紀錄，不更改帳號、Consent 或家屬分享規則。結案後仍可查收案歷史。
- 暫停後的管理入口獨立於照護工作台，避免無法恢復。多筆收案不接受直接狀態命令，需個別審查。

## 資料與授權

`elder_enrollment` 新增正整數 version；新表 `elder_enrollment_change` 保存前後狀態、
原因（最多 120 字）、操作人、版本與時間。複合 FK 綁定收案／長者／tenant，DB trigger 拒絕歷史 UPDATE／DELETE。
既有 ended_at／ended_reason 用於結案；沒有新增長者登入帳號欄位。

新增獨立 `enrollment:read`／`enrollment:manage`。每次查詢重驗 ACTIVE actor、tenant、care unit、
tenant-level 及 unit-level 會員、原建立人、同據點 DAYCARE_ASSIGNMENT 關係及 scope。
寫入同一筆 grant 必須含 read＋manage，不拼接多筆權限；先鎖 Elder 再鎖 Enrollment，等待後重驗授權。
先授權才可重播成功 receipt；expected_version、Idempotency-Key 防止重複操作及覆蓋較新狀態。

新建資料直接給原建立人必要 scopes。Migration 只補齊有效收案、有效建立人及完整原預設權限；
縮限或自訂 scope 不自動擴權。Runtime principal allowlist 新增歷史 SELECT／INSERT，
收案只允許狀態、版本、結案欄位 UPDATE，不允許改 ownership 或有效期間。

四個 API operations 使用 strict schema、標準 envelope、no-store 及 opaque cursor。
`elder.enrollment_changed.v1` 只含 enrollment_id、elder_id、前後狀態、版本；不含姓名或原因。
未完成派案另發既有 cancellation event；domain、撤銷、歷史、outbox、receipt 全部同交易。

## 驗證

- 完整 Frontend：84 files／775 tests；新增面板 9 項、管理頁 3 項。
- Core：完整 unit suite 1650 tests 及 Ruff 全數通過；新增權限 allowlist／schema／鎖後撤權檢查。
- ESLint、TypeScript、Next.js production build 通過。
- PR 前 CI 影響分類／workflow 規則測試 26 項通過。
- 靜態 contracts 及 live Core verifier 通過；117 runtime operations 均有契約。
- 共享 development 上只執行自行包交易的 SQL／HTTP 合成測試；資料與暫時 schema 全回滾。
  覆蓋狀態轉換、必填／偽造欄位、版本、冪等、跨角色／tenant、read-only、撤權、過期恢復拒絕、
  對話取消、當日新收案派案清單、Consent 保留、不可變歷史、舊平板／配對碼失效。
  注入 outbox 失敗證明收案、平板、對話、派案全部回滾。
- Dry run 通過後 additive 套用 development：`e9a1b3c5d768` → `f0b2c4d6e879`；
  70 張業務表、歷史 trigger 均確認；沒有 reset／downgrade。
- Production frontend → 真實 Kinsun 密碼登入／HttpOnly cookie → BFF → Core → Supabase：
  建立合成長者、暫停、恢復、取消結案確認、再確認結案，全部成功。
  恢復 profile GET 200，結案 profile GET 404。兩個合成收案均保留三筆歷史與三筆事件。
- 兩個同時 BFF 請求使用相同 key：200／200、相同 receipt、只有一次狀態轉換；
  相同版本、不同 key：200／409。最終 history versions 4／3／2。
  第一次測試用 JSON 字串順序比較產生假陰性；改為物件內容比較後確認一致，未改產品程式。
- 有獨立 disposable DB 的併發 regression case，使用 committed_session；本機未執行該 fixture，
  避免其 TRUNCATE teardown 破壞共享資料。完整 migration lifecycle／integration suite 仍待 CI。

## UI QA

使用 production build，375／390／430／768／1440 目標寬度驗證服務中清單、表單及歷史，
DOM scrollWidth 等於 clientWidth。Windows browser 回報手機 CSS 寬度約為設定值 + 1px；
未使用 CLI window-size 推定手機尺寸。390 寬度另驗確認、暫停、結案、中英文、唯讀、撤權清除、空資料、載入、錯誤。
確認視窗焦點在 dialog 內；取消不送出；reduced-motion 變體通過。無需更改版面。

畫面證據位於本機 ignored `.qa/local/enrollment/`：
`active-375.png`、`active-390.png`、`active-430.png`、`active-768.png`、`active-1440.png`、
`confirm-390.png`、`suspended-390.png`、`ended-390.png`、`ended-en-390.png`、
`loading-390.png`、`empty-390.png`、`readonly-390.png`、`denied-390.png`、`error-390.png`。
所有截圖已逐張檢視；首次 loading 截圖因回應先完成而捕捉到清單，重新用受控等待截圖後驗證 skeleton。
Skeleton 沿用既有淺色視覺，DOM 確認四條 24px 高的 bars 與 aria-busy 狀態。
錯誤／空資料／撤權版面使用合成 route fixture；真實收案轉換沒有 mock。

## 交付限制

本次未做真人麥克風／聽感、真機及 production 啟用；語音實測依 Owner 指示延後。
合成登入帳號及機構會員已撤權；再次載入真實頁面確認資料清除。臨時 QA 服務已停止。
不涵蓋跨機構轉移、重新收案、非建立人接管、Household、刪除或保存期限決策。
既有讀取可能已在暫停交易提交前開始；服務於後續請求與語音階段 gate 重驗，不能收回已顯示的資料。
runtime principal 權限配置檔已更新，部署時須依既有 runbook 重套角色權限；本次未改共享資料庫登入角色。
原有五個 `.qa/proposal*`／proposal scripts 檔案未納入本次工作。
