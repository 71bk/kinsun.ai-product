# Development 驗證設定輪替待辦

2026-09-14，進行 previous-service-record 真實登入 QA 時，環境診斷指令只遮罩 `NAME=`
前綴，未匹配的值仍輸出到工具紀錄。此文件只列設定名稱，不重述值；原始值不應複製到
issue、PR、一般 log 或其他證據檔。已向 Owner 說明，AGENTS.md／CLAUDE.md 已補上防範規則。

來源是 repository 未版控的 development `.env`；未驗證其他環境是否重用相同值。
沒有證據顯示這次輸出包含 DATABASE_URL、provider API key、測試帳號密碼或 App Session token。

## 已完成的限制措施

- 停止以文字搜尋／替換輸出 `.env` 內容；後續使用 parser 與相等／存在布林檢查。
- QA 僅使用新建的隔離 synthetic 帳號；測試帳號／session／membership 的撤銷結果另記於 QA report。
- 不擅自修改既有登入密鑰或 identity digest，避免使其他帳號無法登入。

## 待 Owner 核准的具體變更範圍

| 設定 | 輪替與驗證 | 相容性影響 |
| --- | --- | --- |
| `KINSUN_AUTH_HANDOFF_SECRET` | 產生新的獨立隨機值，同步注入 BFF 與 Core；重啟並驗證舊值拒絕、新值成功 | 更新不同步時 Email/password 登入暫時失敗 |
| `KINSUN_EMAIL_CHALLENGE_HMAC_SECRET` | 產生新的獨立隨機值；驗證新 challenge，既有 challenge fail closed | 未完成的驗證流程需要重新開始 |
| `KINSUN_SYNTHETIC_EMAIL_CODE_SECRET` | 更換 development synthetic code，驗證新流程 | 使用者需要新的 development 驗證碼；不是 production delivery |
| `KINSUN_IDENTITY_HMAC_SECRET` ＋ `KINSUN_IDENTITY_HMAC_KEY_VERSION` | 先確認現有 KINSUN identities 的受治理 Email 來源及遷移方法，再產生新 key、提升版本並交易式更新精確 rows | 現行 lookup 只使用一組 key/version；直接更換會使舊帳號無法被找到，不能只改 `.env` |

執行前須確認是否跨環境重用，以及 Owner 是否允許既有 synthetic/demo 帳號的登入中斷與
identity 遷移。現行 QA 授權僅涵蓋新建隔離帳號，不涵蓋這些既有登入設定。
不得把本文件視為已完成輪替，也不得為此建立明碼 Email 或 secret 清單。
