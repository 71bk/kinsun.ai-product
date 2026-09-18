# 文字陪伴回覆朗讀

文字聊天回覆下方可按「播放回覆」，並可停止、重新播放。播放只使用 Core 已授權的
`speech_synthesis_text`、語言與一次性 capability，不重送使用者文字、不重新執行陪伴回合。
目前支援國語與英文；台語、客語與 feature-off 回覆維持文字。

## 本機設定

根目錄、不提交的 `.env`：

- `SPEECH_SYNTHESIS_CAPABILITY_ENABLED=true`
- `SPEECH_SYNTHESIS_CAPABILITY_HMAC_SECRET`：獨立、隨機產生的 32 bytes 以上密鑰。
- `SPEECH_SERVICE_IDENTITY_ENABLED=true` 與既有 Speech → Core 身分密鑰。

`services/speech-gateway/.env`：

- `CORE_API_SERVICE_IDENTITY_ENABLED=true`，身分密鑰與 Core 對應設定相同。
- `TTS_CLIENT_IP_HASH_SECRET`：另一個獨立的 32 bytes 以上密鑰，本機合成也需要。
- `AZURE_SPEECH_KEY` 與 `AZURE_SPEECH_REGION` 必須來自同一 Azure Speech 資源。
- 國語／英文 provider 使用 `azure-speech-tts`。

前端 `.env.local` 設定 `NEXT_PUBLIC_SPEECH_GATEWAY_URL=http://127.0.0.1:8002`。
修改設定後重新啟動對應服務；完整既有設定見 [協作者設定](COLLABORATOR_SETUP.md#11-speech-gateway-與語音選配)。
Repository 範例旗標仍預設關閉；密鑰不得提交。

## 行為與限制

- 首次按播放時才合成；capability 預設 60 秒有效，過期時保留文字並提示送出新對話。
- 成功取得的音訊只存在當前頁面的記憶體，重播不再呼叫 Azure 或重用 capability。
- 開始新對話、送出下一輪、切換輸入模式／長者或離開頁面時，中止請求、停止播放並釋放音訊。
- 合成等待上限 35 秒。Azure、授權或網路問題只影響語音，文字回覆與記憶 receipt 仍保留。
- 瀏覽器若拒絕播放，提供再次點擊重播；不因此再次消耗合成憑證。
- Gateway 健康檢查成功不代表 Azure 金鑰有效，須另外驗證實際合成。

## 驗證範圍

元件測試涵蓋 capability／語言／到期 gate、單次合成、停止與重播、瀏覽器拒播、provider 失敗、
離開頁面的取消與過期回應隔離。瀏覽器視覺測試使用合成 API fixture 和 WAV 音訊，與真實
Azure 合成、登入／Core／資料庫整合分開回報。

2026-09-17 本機驗證：相關測試 34 passed、frontend typecheck、變更檔案 ESLint、production
build 與 `git diff --check` 通過。Chrome 合成 Browser QA 在 375／390／430／768px 驗證
鍵盤操作、實際 WAV 解碼與播放進度、停止、無第二次合成的重播、對話切換清理、feature-off、
provider 失敗與 reduced-motion；播放按鈕高 66.5px，沒有水平溢出。

Supabase 唯讀確認 `service_identity.speech_synthesis_claim` 已存在，revision 為
`b6d8f0a2c435`；Core／Gateway 健康檢查 200，Gateway 對無效 capability 回 401。
Azure 真實 adapter smoke 回 `authentication`，尚未取得有效音訊；需更新配對的 Speech
資源金鑰與 region 後重驗。未完成真實帳號 → Core → Gateway → Azure → Browser 的完整 E2E，
上述合成 Browser QA 不能替代它。
