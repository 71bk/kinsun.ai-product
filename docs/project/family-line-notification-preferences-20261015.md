# 家屬 LINE 每日通知設定

工作期間：2026-10-13–15。本次範圍是家屬自行管理通知偏好，不代表真實 LINE 推播或排程已上線。

後續已完成 [單次排程入口與服務身分驗證](line-notification-scheduler-20261015.md) 的本機／合成驗證。下方「worker 只有 README」記錄本設定切片交付時的狀態；每日觸發部署與真實收訊仍未完成。

## 已完成的功能

- 家屬頁面 `/family/notifications`，中英文與持續導覽。每位家屬只管理自己對目前長者的開關，不依簽約人身分。
- `GET /api/v1/family/elders/{elder_id}/line-notification-preference` 與相同路徑的 `PUT`。未建立偏好時回傳關閉、version 0，GET 不建立資料。
- 每次重新確認 active actor／tenant／長者、tenant-level FAMILY_MEMBER membership、照護讀取權限、當前 FAMILY_SHARING 同意及自己的 DAILY／ALL 家屬分享關係；失效或跨範圍一律不揭露地拒絕。
- 只接受 `line_enabled` 與 `expected_version`，收件人由 session 決定；版本衝突回 409，idempotency replay 也重新確認授權。設定變更與最小 outbox 事件同一交易完成。
- 顯示未綁定、已綁定收件帳號、需要重新綁定、服務未開放及不支援的舊排程。只有 LINE 登入但沒有加密收件目的地，不會被視為可推播。
- 服務未開放或舊排程不符合條件時，仍可關閉 LINE，保留 EMAIL／IN_APP 通道與其他設定。舊資料若 LINE 已開但時間為 NULL，也不會被誤標為 READY；原本未開 LINE 的 DAILY 預設首次開啟時才補 08:00。
- 固定台灣時間每日 08:00，沿用既有 sender 的前一日已發布 DAILY 日報與 `recipient_scope` 過濾。LINE 訊息維持日期及登入連結，照護內容仍須登入後授權讀取。
- 家屬設定頁會在重新整理、視窗回到前景及定期檢查時重新讀取；舊 request 在長者切換或離開頁面後不能覆蓋新狀態。儲存成功後再 GET，避免把 idempotency 的歷史 snapshot 當成最新設定。
- 手機導覽維持完整文字；語言切換在窄幅容器改為整個選項換列。通知卡片依容器寬度縮減留白，200% 放大時保留英文完整單字與按鈕文字。

## 資料庫與契約

Development 已由 `f0b2c4d6e879` 升級至 `a1c3e5f7b902`：只新增既有 `notification_preference.version`，default 1、NOT NULL、正數檢查，業務表仍為 70 張。沒有 reset、truncate、downgrade 或批次改寫收件偏好。

新增兩個 domain schema、成功 envelope、正負 examples 與 OpenAPI GET／PUT。匯出器增加 `--schema`／`--path`，只更新指定部分，保留既有人工補充的操作與規格。Core live verifier 已涵蓋兩個新操作。

Outbox 使用 `family.notification_preference.updated.v1`，payload 只有開關與版本；actor／tenant／同意版本位於受保護的事件 metadata，不存 LINE subject、digest、密文、憑證或照護內容。

## 驗證證據

| 項目 | 結果 |
| --- | --- |
| Core 首次完整 unit | 1848 passed；另 1 項既有 Hypothesis 測試首次超過 200ms deadline，非斷言錯誤 |
| 上述超時測試單獨重跑 | 1 passed，未修改測試 deadline 或產品授權規則 |
| 最終通知偏好與既有 sender 定向測試 | 29 passed，包含新增的 24 項偏好測試 |
| Frontend 完整回歸 | 844 passed，90 files；後續語系／共用 UI／家屬定向回歸 63 passed |
| Core lint／format、Frontend lint／型別 | 通過；正式 build 另含 TypeScript 檢查 |
| 靜態契約與 Core live verifier | 通過；新 GET／PUT 未登入時 fail closed |
| 真實 SQL／HTTP | 兩位合成家屬獨立 opt-in、同 key 不跨 actor、重播、過期版本、關閉保留 EMAIL、缺時間的舊偏好、membership／關係／scope／同意／actor 失效與跨 tenant／角色；整個 fixture 外層 rollback 通過 |
| 真實登入 BFF | 9 項通過：匿名拒絕、家屬登入與範圍清單、讀取自己的設定、頁面、兩角色 CSRF、照服員角色拒絕；兩個暫時 session 已登出及刪除 |
| 正式建置 | 最終 source 的 production build 與 TypeScript 通過，使用 1 worker |
| 最終 RWD／放大 | 中英文 34 個合成狀態通過：375／390／430／768／1024／1440、綁定與服務狀態、離線 opt-out、儲存回讀、401／403／404 清除資料、鍵盤焦點、reduced motion；390 寬度以 CSS zoom 2 實際放大，額外檢查英文完整單字，並人工核對截圖 |

完整回歸的 timing failure 與獨立重跑分開記錄，不能寫成一次全綠的完整 Core 執行。最後追加的舊時間邊界及 repository 整理另有定向 unit 與 SQL／HTTP rollback 重驗。

本機細節與合成截圖保留在忽略的 `.qa/local/line-notifications-20261013/`。初期 QA 腳本對 production cookie 名稱、scope endpoint／必要 mode 參數及 route announcer 的假設已修正；沒有為測試放寬產品 gate。第一輪 cookie 名稱不符留下的一個 QA session，已依本次 Core 啟動時間與同一 demo actor 精確識別、撤銷及移除；沒有清除其他使用者 session。

視覺 fixture 使用 production session cookie，並確認 SSR 顯示登出按鈕；API 回應以合成資料攔截，不能代替上一列真實登入 BFF 或真實收訊證據。最後重啟曾遇到埠釋放／服務 readiness 的短暫時差；核對本輪 PID 與埠後重驗通過，沒有停止其他服務。

已核對命令、埠與 Python 完整父子關係，停止本輪專用前端與 Core；3110／8110 剩餘 listener 為 0。合成瀏覽器 contexts 已關閉，資料庫 workflow 已 rollback，暫時登入 session 已清除；既有日常服務未列入停止範圍。

## 尚未完成的外部條件

1. 正式 LINE 官方帳號／Messaging API 設定與收件綁定的實際串接驗收；本次沒有變更 `.env` 或啟用通知旗標。
2. 每日排程接線與部署。`services/notification-worker` 仍只有邊界 README，尚無可執行 worker／scheduler deployment。
3. 由使用者指定測試收件人後，驗證真實收到、登入開報表、關閉與撤權後不再產生新的通知；本次未呼叫真實 LINE 推播。

平台／region／預算仍待選定，未建立 production IaC，也沒有部署、commit 或 push。已送出的 LINE 訊息不在本次偏好開關可回收的範圍。
