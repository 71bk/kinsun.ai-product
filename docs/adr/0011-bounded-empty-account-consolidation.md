# ADR 0011：Google／LINE 空白重複帳號的受限合併

- 狀態：Accepted
- 日期：2026-08-12
- Owner：Project Owner
- 相關：[ADR 0010](0010-provider-neutral-oidc-and-application-sessions.md)

## 背景

使用者可能先以 Google 建立一個 Actor，之後又以 LINE 建立另一個 Actor。單靠 email、顯示名稱或瀏覽器狀態，都不足以判定兩個 Actor 屬於同一人；直接搬移正式照護資料也會破壞 consent、tenant scope、稽核與外部通知目的地的語意。

目前需要支援的是一個更窄的情境：使用者能同時證明 Google 與 LINE 身分，而且 LINE Actor 只包含登入後自動建立、尚未使用的 ELDER onboarding 骨架。

## 決策

Core 提供 explicit linking 與「空白帳號受限合併」，但不提供一般性的 Actor merge。

流程必須同時滿足：

1. 目前登入的是有效且最近 10 分鐘內重新驗證的 Core App Session。
2. 目前 Actor 已有 active Google identity。
3. 使用者在同一個 linking transaction 中完成新的 LINE OIDC 驗證；state、nonce、PKCE 與 App Session fingerprint 全部相符。
4. LINE subject 已屬於另一個 active ELDER Actor 時，Core 才評估是否為可合併的空白骨架。
5. 使用者必須在短效、單次使用的 merge confirmation token 到期前再次明確確認。

只有下列條件全部成立才可自動合併：

- 來源 Actor 是 active ELDER。
- 來源 Actor 恰好只有一個 active LINE identity。
- 來源 Actor 恰好只有一個 active ELDER membership、一個 active Elder 與一個 active HOUSEHOLD tenant。
- 該 tenant 沒有其他 membership 或 Elder。
- 除 onboarding 骨架與允許的 onboarding outbox event 外，沒有任何 tenant、elder 或 actor 關聯資料。
- LINE identity 沒有加密的 Messaging API push destination。
- 目標 Actor 尚未有 active LINE identity。

任何條件不成立，Core 都回傳 `MANUAL_REVIEW_REQUIRED`，並保留 `PENDING_REVIEW` 紀錄；系統不自動搬移或刪除正式資料。

## 合併交易

確認交易會在 row lock 與資料庫 transaction 下重新檢查所有條件，避免檢查後資料改變：

- 撤銷來源與目標 Actor 的所有 active App Sessions。
- 將來源 LINE identity、Actor、membership、Elder 與 tenant 標記為 inactive/revoked；不硬刪資料。
- 在目標 Actor 建立新的 active LINE identity。既有 identity 不改寫 `actor_id`，以保留 App Session 外鍵與歷史語意。
- 寫入不含 raw provider subject、token 或 email 的 outbox audit event。
- 發行一個綁定目標 LINE identity 的新 App Session，交由 BFF 原子替換 Cookie。
- 將 merge request 標記為 `COMPLETED`；token 在資料庫只保存 SHA-256 digest。

## 安全與失敗策略

- private Core endpoints 同時要求 BFF shared-secret authorization 與 App Session bearer，缺一即拒絕。
- merge token 為 256-bit opaque credential、預設 10 分鐘有效、單次使用，並綁定來源 identity、目標 identity、Actor 與啟動流程的 App Session。
- callback Cookie 只保存簽章 transaction 或簽章 merge envelope，不保存 raw App Session、LINE subject 或 provider access token。
- 併發、過期、Session 改變、資料新增、身份狀態改變或唯一性衝突一律 fail closed。
- 自動流程只處理 ELDER onboarding 骨架；FAMILY、STAFF、Admin、Content Manager，以及任何已有照護或通知資料的帳號都不在範圍內。

## 後果

優點是可以安全處理最常見的空白重複帳號，同時維持 Actor、Session 與稽核歷史。代價是正式資料的帳號仍需要獨立設計人工審核、衝突解決、consent 遷移與 rollback 工具；這些工作不得擴充本 ADR 的自動合併條件來替代。

## Rollback

可先關閉 LINE direct/linking runtime gates，停止建立新 merge request。既有 `PENDING_CONFIRMATION` 可批次標記為 `REVOKED`；`PENDING_REVIEW` 保留供稽核。已完成的合併不得用自動反向 migration 還原，因為完成後可能已有新的 Session 或 domain activity，必須走人工、可稽核的復原程序。
