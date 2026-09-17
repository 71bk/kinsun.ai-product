# ADR 0022: 本人自述的陪伴記憶獨立於正式照護覆核

- Status: Accepted (2026-09-17 Owner 指示實作錄影展示)
- Partially supersedes ADR 0014：限本決策的低風險本人自述分支；其餘分級、支持決策與確認規則仍有效。

## Decision

已登入的長者本人開啟 LONG_TERM_MEMORY 且明確同意 `personal_memory_auto_save=true` 後，Core 可從成功且 ALLOW 的 BASIC_VOICE
文字回合擷取明確第一人稱的一般音樂、嗜好、稱呼、飲食偏好及有限早餐習慣。
使用 Core-owned 有界語法及允許詞彙，不相信模型輸出的 risk/confidence 或「已記住」宣稱。
否定、他人、過去、條件、疑問、複合歧義或不支援的句子不自動保存；不建立醫療／敏感推測。

本切片以明確中文自述為可驗收範圍，不宣稱任意語句、多語或多人語音均支援。
支援型／代理需求 profile 不走自動保存。一般記憶不再依附 Care Event VERIFY，亦不自動
生成正式照護事實；既有事件擷取與覆核流程保留，避免把偏好等同某日實際攝取。

記憶保存最小 normalized statement、session／turn、本人與 policy 證據，不保存完整對話。
以獨立 policy version 標記；同類別保留一筆目前自述，重複不增加版本，變更建立 immutable
版本。使用長者資料列鎖序列化此分支，與刪除／修正協調。

Core SQL 是本分支的讀取權威，不依賴 Graph projection 就緒，也不偽造 SYNCED。
每次讀取仍檢查 scope、Consent、本人來源、版本／digest、profile、有效時間與刪除狀態。
舊版人工確認記憶保留既有 final gate，沒有批次轉成自動可信。
舊同意沒有這個 scope，不會默認升級；需在新說明下重新開啟。功能還需
`EVIDENCE_AWARE_MEMORY=true` 與 `PERSONAL_MEMORY_ENABLED=true`，出廠均關閉。
`AUTO_LOW_RISK_MEMORY` 是既有事件分支，獨立保留，展示不需開啟。

回合成功後以 Core receipt 顯示「已記住」及撤銷；記憶頁可查看、修改與刪除，明示為本人
自述。修改重新通過相同內容規則。停止記憶後不再保存／取用，保留獨立刪除能力。

## Acceptance

1. 開啟同意後說「我喜歡聽老歌」得到保存 receipt，不需照護者操作。
2. 建立新 session 問喜好，真實 provider 從 Core 授權背景回答；不以寫死回覆冒充記憶。
3. 相同陳述不重複；修改後只讀新版本；撤銷／刪除／停止用途後新 session 不讀舊內容。
4. 他人、跨 tenant／elder、否定／轉述／過去／敏感內容與失敗回合零自動保存。
5. PostgreSQL、API contract、前端元件與正式建置畫面驗證；合成帳號實測並記錄環境邊界。

## Deferred

依日期檢索昨天早餐、任意語句的模型擷取、多筆同類偏好相關性排序與語音自動保存另行擴充。
本切片的日常記憶不是正式照護資料，也不是 ChatGPT 內部實作的複製。
