# 語音新增個人記憶

決策：[ADR 0023](../adr/0023-self-stated-voice-memory.md)。

## 使用

1. 本人登入後，到「記憶與同意設定」。舊同意若未包含語音，先停止長期記憶，再閱讀新說明並開啟。
   重新同意會建立新版，原同意下的記憶不會自動沿用到 AI 背景；不刪除原資料。
2. 回首頁選語音，按「開始說話」，說「請叫我王大爺」，再按說完。
3. 辨識不確定時核對文字；內容正確才選「對，就是這樣」，不正確就重說。
4. 回合成功後確認出現「已記住：請叫我王大爺。」。只有模型說記住不代表已保存。
5. 下一輪問「你知道該怎麼稱呼我嗎？」。也可在我的記憶查看／修改／刪除，或按 receipt 的撤銷。

目前支援音樂、嗜好、稱呼、飲食偏好與早餐習慣的既有中文句型；同類以新陳述更新。
沒有記憶同意時仍能一般陪伴，但不會新增。TTS 不可用時，文字回答與保存提示仍可查看。
功能需 Core 的 `EVIDENCE_AWARE_MEMORY`、`PERSONAL_MEMORY_ENABLED`、`ASR_GATE_ENABLED` 啟用，
有效 ASR HMAC 與既有 Speech Gateway 接線正常。不需要資料庫 migration。

## 驗證範圍

單元測試涵蓋來源／原文綁定、辨識確認、舊同意拒絕、本人與 tenant 邊界、失敗回合不保存，
以及前端 receipt、版本撤銷、衝突、播放失敗與切換使用者時丟棄延遲回應。
實際 PostgreSQL synthetic lifecycle 以每次完整 rollback 驗證文字、ALLOWED 語音與
CONFIRMED 語音的保存／讀回、來源變更排除、修正／過期版本拒絕／刪除與撤回同意。
沒有使用 Supabase 執行 schema rebuild、downgrade 或一般 integration conftest。

麥克風真實辨識品質與使用者帳號完整操作仍需實機確認；不以合成資料驗證替代。
