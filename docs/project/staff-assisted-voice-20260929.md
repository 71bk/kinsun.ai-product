# 照服員協助無帳號長者使用語音（2026-09-29）

對象是不會操作電子設備、但能表達使用意願的長者。沿用 ADR 0013 的 Account／Elder
分離：照服員登入自己的帳號，長者維持沒有 Actor／登入身份的照護主體。

## 操作流程

1. 照服員建立長者資料，或從已授權長者詳情開啟「準備陪伴平板」。準備失敗可單獨重試，
   不會重新建立長者。重新準備會使舊平板時段失效。
2. 向長者說明 AI 用途、處理對話、醫療限制與停止方法。只有長者本人清楚表達願意使用，
   才勾選確認並記錄口頭意願。無法表達意願或需要代理授權時，此流程不提供代為同意。
3. 用一次性連結開啟平板長者模式；同台裝置的照服員 cookie 會清除。照服員協助選擇華語
   或 English，按「開啟語音陪伴」並允許麥克風。
4. 聲音由本機靜音偵測分段，送既有 Speech Gateway → Core ASR gate → Agent → TTS
   capability 流程。每段最多 15 秒，說話後停頓約 1.4 秒送出，播放完再收下一段。
5. 低信心只重錄，不替長者做 ASR 本人確認。重試提示只使用瀏覽器本機語音讀固定文字，
   不把對話或 AI 回覆送進瀏覽器語音合成。無本機語音、連線／播放失敗、連續兩段無聲
   或低信心都會暫停收音；每次開啟最多 12 段。
6. 聆聽時說單獨的「停止」／「結束」或 "stop" 可結束時段。播放期間可由照服員按暫停；
   這個切片沒有播放時的插話辨識。離開頁面或暫停都釋放麥克風。

## 資料與授權

- 唯一新增 SQL 欄位：`eldercare_ai.conversation_session.assisted_session_id`，nullable UUID
  FK → `assisted_elder_session.assisted_session_id`，有索引。一般對話／歷史資料保持 NULL。
  Alembic `d8f0a2b4c657`（前版 `c7e9f1a3b546`）已 additive 套用 Supabase development。
- 沿用 `consent_grant.scope` JSON 加 `assistance_method=STAFF_RECORDED_VERBAL`。
  `granted_by_actor_id=NULL`、`recorded_by_actor_id` 是實際 worker；只記錄 BASIC_VOICE。
  既有有效同意不自動升級用途或改寫來源。
- 新增四個 POST：`/elders/{elder_id}/assisted-sessions/{assisted_session_id}/acknowledgement`、
  `/assisted-elder-sessions/current/voice-tickets`，以及其
  `/voice-sessions/{session_id}/companion-turns`、`/cancel`（皆在 `/api/v1` 下）。
- Speech ticket consume／ASR／Agent／TTS 每次查當前有效 handoff、initiator 關係、tenant、
  Elder 和 BASIC_VOICE 版本；舊平板及其票證不能跨到新的陪伴時段。
- BFF 僅從 HttpOnly elder-session cookie 取憑證，驗同來源、路徑與 payload allowlist。
  沒有新增 Memory、event extraction、family sharing 或正式代理人能力。

## 環境與驗收

Core 需要既有 `ASSISTED_ELDER_SESSIONS_ENABLED`、`VOICE_TICKET_ENABLED`、`ASR_GATE_ENABLED`、
`SPEECH_SYNTHESIS_CAPABILITY_ENABLED`、`SPEECH_SERVICE_IDENTITY_ENABLED` 及相應獨立 secrets。
Speech Gateway 需正確 Core 位址、service identity、Deepgram／Azure provider 設定；前端需
`NEXT_PUBLIC_SPEECH_GATEWAY_URL`，獨立 QA 埠另設相符的 `FRONTEND_ORIGIN`。仍禁止 Production
開啟 assisted sessions，committed default flags 不變。

已驗證：

- Core unit：1,624 passed；Core Ruff check／format（446 files）通過。
- Core static contracts 與 live verifier 通過，106 runtime operations 均列入契約。
- `scripts/qa/verify_assisted_voice_rollback.py` 通過：真實 SQL＋ASGI HTTP，合成 worker／
  Speech identity 與 Agent；全部 fixture 寫入 rollback。涵蓋無 Actor 建立、口頭確認來源、
  單次配對、低信心阻擋、高信心 Agent/TTS capability、無 Memory、換發、跨時段拒絕、撤回。
- 前端完整 suite：80 files／750 passed；其後補查陪伴與照護待辦並存權限及 recorder
  cleanup，受影響兩檔 43 passed（新增 1 case）。長者頁另 4 passed；最終 build、型別、
  lint 與 diff whitespace check 通過。
- 開 PR 前 CI tooling：`python -m unittest discover -s scripts/ci -p 'test_*.py'`，26 passed。

Browser QA 使用正式 production build 與合成 HTTP／MediaStream，沒有使用真人麥克風。
375／390／430／768／1440 CSS px 都檢查 idle、麥克風拒絕、聆聽、暫停、既有長者、
口頭意願尚未勾選及確認後交付；另查建立長者後準備平板，合計 36 個狀態。390 使用
reduced-motion。每個狀態均檢查水平 overflow；暫停後合成 track 已 stop。截圖置於
`.qa/local/assisted-voice/`，代表圖為 `voice-idle-375.png`、`staff-explanation-390.png`、
`voice-listening-1440.png`。可讀文字與主按鈕沒有裁切／重疊；手機標題換行是大字體
響應式排版。檢視發現收音時仍顯示「請開啟語音」舊提示，已改為依目前狀態顯示文案。
重新 build／啟動後，五種寬度全部重驗聆聽狀態、正確提示、無水平溢出及暫停後 track stop；
新截圖為 `voice-final-{width}.png`，390 reduced-motion 亦通過。真機操作手感、實際音訊、
Lighthouse 與 production 部署均不在此證據範圍內。

後續 Azure 實測：先前請求回 `authentication` failure（provider 401／403 分類）；本機原
區域 `eastasia` 與資源頁不符，改成 `japanwest` 後仍被拒絕。更新使用者提供的金鑰後，
現有 Azure Speech TTS adapter 成功把固定測試句合成 `audio/mpeg`（30,960 bytes）。
金鑰僅寫入 ignored 的 `services/speech-gateway/.env`，音檔置於 `.qa/local/`，均未提交。
此探測之後，已完成下列真實服務驗證；真人麥克風與主觀聽感仍待使用者確認。
沒有 disposable `TEST_DATABASE_URL`，未執行會 reset schema 的完整 integration／migration
升降版測試；development DB 未被 reset、truncate 或 downgrade。

### 真實服務串接（同日追加）

正式前端 build 連線 Core 8000、Agent 8001、Speech 8002。以獨立合成照服員真實 Email／
密碼登入，從 UI 建立一位無帳號長者、記錄合成情境下的口頭確認，再以一次性連結配對
新瀏覽器 context。沒有攔截或 mock HTTP、身分驗證、資料庫或雲端供應商；只有收音來源
使用固定合成音訊的 MediaStream。新增 fixture 有獨立 tenant／worker／policy，工作身分
與政策有效至 2026-09-29 20:19（Asia/Taipei）；保留稽核紀錄，不 reset 共用資料庫。

- 兩輪華語對話經 Deepgram `nova-3:2026-04-01.30000`、Core gate、Gemini
  `gemini-3.6-flash`、Azure `japanwest` 合成並進入瀏覽器播放；第一輪播放完成會自動續聽。
  第二輪播放中按暫停後，所有合成收音 track 均為 `ended`。
- 連續兩段無聲自動暫停，沒有發出 ASR 請求。噪音造成空辨識時，Speech 回 422、Core
  將該輪標為失敗，前端停止收音；後續 best-effort cancel 的 409 是已終止狀態的拒絕。
- 另一段噪音得到真實 ASR confidence `0.0762`，Core 回 `CONFIRMATION_REQUIRED`，
  前端取消該輪；SQL 確認沒有 AgentRun、沒有偽造長者確認。驗收發現 `getVoices()` 首次
  回空陣列，稍後 `voiceschanged` 才提供 6 個聲音（含 3 個本機華語聲音）；已改為最多
  等待 2 秒載入，只接受同語言本機聲音，取消或逾時會移除 listeners。仍不使用雲端
  瀏覽器語音或替代語言，真正無可用聲音時依設計暫停。
  修正後 production build 重測：固定本機提示收到原生 `start`／`end` 事件並恢復聆聽；
  第二次真實低信心會暫停，沒有 Agent 請求，track 為 `ended`，390 px 無水平溢出。
  延遲語音清單、已載入聲音、取消、逾時、遠端聲音及錯誤語言拒絕的回歸與相關語音
  測試共 19 passed；ESLint、正式 build 與 TypeScript 檢查通過。
- 合成語音「停止」經真實 ASR 辨識後取消該輪、結束平板時段並回到配對頁；全部 track
  釋放，沒有將停止命令送至 Agent。
- 重新準備平板後，舊 current／取票／Agent 請求回 401、舊 ASR 票券回 403、舊 TTS
  capability 回 401。TTS 檢查當時距原定到期仍有 33 秒，確認拒絕來自換發失效。
- SQL 讀回一位 Elder 的 `actor_id=NULL`、同意只有 BASIC_VOICE、實際照服員為 recorder、
  所有語音 session 綁定 handoff；Memory 新增數為 0。

機器可讀摘要見 [live verification](staff-assisted-voice-live-20260929.json)。原始安全摘要、
測試音檔與截圖放在 ignored `.qa/local/assisted-voice/`。本機 launcher 只在服務程序內
啟用所需語音 gates 與獨立服務驗證 secrets，沒有改變 committed defaults；真人測試頁
使用全新、未替換 `getUserMedia` 的 context。以上不構成真人收音、真機喇叭聽感或
Production 驗收。PR #62 在 `b7d34af` 的 10 項 GitHub checks 全數通過。
