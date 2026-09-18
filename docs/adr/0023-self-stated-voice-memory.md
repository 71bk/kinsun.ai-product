# ADR 0023: 本人語音的低風險個人記憶

- Status: Accepted（2026-09-18，Owner 要求「目標是可以用語音新增」）
- Extends ADR 0022 的輸入來源；其餘用途、詞彙、風險、profile、版本與刪除規則不變。

## Decision

已登入的長者本人可從成功且 ALLOW 的 BASIC_VOICE 語音回合保存支援的明確自述。
沿用 Spec 18 的 Elder-only voice session：本人帳號、本人開啟同一 session、Core ASR Gate
授權同一份逐字內容。不宣稱聲紋驗證，也不允許照護者、家屬或無帳號交接 session 自動保存。

LONG_TERM_MEMORY 必須同時包含 `personal_memory_auto_save=true` 與新的
`personal_memory_voice_auto_save=true`；新欄位預設 false，舊同意不自動擴張。
使用者在更新後的同意畫面自行閱讀、確認。重新同意依原規則建立新版，舊記憶不自動重綁。
使用既有兩項記憶 feature flags，ASR Gate 也須啟用，不增加 provider key 或資料表。

Core 將已授權的 ASR evidence 傳入保存服務；保存時再驗 session、tenant、elder、狀態、
有效期限、原文 HMAC，低信心內容必須由本人明確 CONFIRM。保存最小正規化句子，不新增
完整逐字稿或音訊保存。語音來源使用 `core-self-statement-voice-v1` extractor 與 ASR evidence
reference；不偽裝為 authenticated text。UI 修正保留原來源類型與 evidence reference。

讀回仍須目前同意、目前 ACTIVE 版本、digest、profile、未刪除及同 tenant／elder。
語音來源另查完成的本人 session、對應 ASR evidence 與 ALLOWED／本人 CONFIRMED 狀態。
ASR TTL 只限制新回合處理；已成功保存的記憶不會因辨識憑證到期立即失去可讀性。

語音頁只依 Core receipt 顯示「已記住」及 version-bound 撤銷。TTS 或瀏覽器播放失敗不代表
記憶未保存，receipt 必須保留。回應中斷時提示到記憶頁確認，不斷言「未保存」。

## Scope

沿用中文有界句型，包含「請叫我王大爺」、「我每天早餐吃粥」。不將「教我」擅自改成「叫我」；
辨識誤字可重說，或於文字輸入／記憶頁修正。任意語句、聲紋辨識、純語音撤銷及多筆同類
偏好排序均不在本增量。語音轉文字 provider 的辨識品質不由此變更保證。
