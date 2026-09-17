# Kinsun｜2026 中華電信智慧創新應用大賽準備度審查

- 審查日期：2026-09-16（Asia/Taipei）。
- 程式基準：`71bk/kinsun.ai-product`，`main`，`acc84ef8a6b02ff8a432f38acf0c41da10dffd3f`。
- 審查目錄：`D:/Hackthon/kinsun.ai`；開始時無未提交修改。
- 授權範圍：唯讀程式／配置／歷史證據、執行既有隔離測試、產出本報告。未改產品、測試、環境設定、資料庫、分支或部署。
- 依據：工作區根層 `KINSUN_CHT_2026_READINESS_REVIEW.md`。本報告是證據盤點，不是官方資格核定或正式營運認證。

## 1. 一頁結論

> 2026-09-17 後續修正：已補上家屬報表讀取的即時 share scope 重驗，以及摘要來源事件
> 檢視／指定日期重新產生 UI；驗證邊界見[交付紀錄](../../project/report-scope-summary-workflow-20260917.md)。
> 以下保留 2026-09-16 審查時的證據與判斷；此增量不代表 Memory 疑點已修復、
> 原始逐字片段已提供或主 Demo 已完成真實全程驗收。

**專案方向符合「智慧醫療／高齡照護」主題，現有軟體成果足以支撐初賽提案；目前尚不能判定行政文件已齊，也不能把完整語音、智慧記憶、AIoT 與通訊韌性一起宣稱為已完成。**

| 判斷面向 | 結論 | 依據與條件 |
| --- | --- | --- |
| 初賽送件 | **CONDITIONAL** | 主題契合、已有可核對程式與驗收。資格、舊團隊成果使用權、正式提案與上傳狀態待團隊確認。這不等於報名完成。 |
| 目前 Demo：路線 A，既有軟體主線 | **CONDITIONAL** | 真實登入、文字 Agent→事件→人工覆核→待辦，以及 B03／B04 有歷史本機驗收；本次沒有重跑完整主劇本。語音及 Memory 啟用條件尚未就緒。 |
| 決賽前交付：限縮後路線 A | **PLAUSIBLE_WITH_CONDITIONS** | 假設至少一位熟悉專案的開發者可投入、可取得新隔離展示帳號及 provider 使用條件，先完成可重現的中文軟體劇本；不承諾全語言、一般化自動記憶或正式營運。實際人力未知。 |
| 路線 B／C | **HIGH_RISK／INSUFFICIENT_EVIDENCE** | 未找到感測接入、裝置歷史歸屬、Fusion、個人基準或離線持久化補送實作；硬體、API、場域與人力亦未確認。 |

### 現在最有證據的展示旅程

1. 長者以原生帳密登入，提交**合成文字**內容；歷史驗收實際經 BFF→Core→Gemini→Core→Supabase。
2. Core 建立待覆核事件，Agent 的行動 proposal 保持私有；照護者 VERIFY 後才出現可採用候選。
3. 照護者檢視並採用候選，建立可追蹤的自我指派待辦；可展示開始、延期、完成、取消及版本衝突。
4. 另有 B03 類型／時間修正、B04 來源篩選、同 key 重送及撤權拒絕的真實登入驗收。

上述不是本次重演，也不是從現場麥克風到語音播放的證據。家屬發布報表、Memory 保存後再次引用，不應直接接在這條已驗收故事末端並標示「全程已驗證」。

### 最重要的三項缺口

1. **送件與權利狀態未確認**：正式提案、同意書、組別／成員、舊團隊使用權及上傳完成證據。`SUBMISSION_BLOCKER / EXTERNAL_UNKNOWN`。
2. **主 Demo 尚未凍結並完整重演**：本機配置的 ASR Gate 與 Memory rollout 都關閉；目前只確認 Core 8000 health 可回應，其他約定展示埠未回應。`DEMO_BLOCKER`。
3. **商業與中華電信連結缺乏直接證據**：有 Persona／需求假設，未找到買方訪談、試用量測、實際單位成本或 CHT API 整合證據。`CLAIM_BLOCKER / EXTERNAL_UNKNOWN`。

另有兩項安全查核疑點，見第 6 節：Memory all-of 語意檢查不足的靜態證據，以及家屬報表縮限 share scope 後的讀取重驗缺口。既有測試全綠不代表這些情境已被覆蓋。

**建議先補初賽文件，選路線 A。** 單一感測來源可寫成有前置條件的決賽擴充；離線／自動 5G 切換不列承諾。這樣能集中展示目前已有證據的治理與照護流程，但需用具體商業規劃補足 CHT 業務連結。

## 2. 官方條件與行政準備

2026-09-16 重新讀取[官方賽事頁](https://cht5g.com.tw/index-smart.html)、[官方 FAQ](https://cht5g.com.tw/)及[競賽辦法 PDF](https://cht5g.com.tw/files/智慧創新應用大賽/01.【競賽辦法】2026中華電信智慧創新應用大賽.pdf)（11 頁，115 年 4 月版）。以下與工作區任務書交叉核對；並未查閱團隊的私人身分證明或合約。

| 項目 | 本次結果 | 下一步 |
| --- | --- | --- |
| 主題適合度 | **符合主題方向**。官方智慧醫療列高齡照護、居家照護、長照 3.0；產品具有對應角色與流程。這是適合度判斷，非主辦核定。 | 優先以智慧醫療／高齡照護撰寫。 |
| 截止 | 官網仍列 **2026-09-18 12:00**。 | 截止前完成文件與上傳；以主辦最新公告為準。 |
| 組別／成員 | **待團隊確認**：校園或社會組、人數、代表人、國籍及排除身分。 | 官方每隊 1–6 人，至少一位臺灣籍；混合學生與社會人士依 FAQ 報社會組。未成年另確認同意要求。 |
| 必繳文件 | 在本次工作區文件搜尋未找到已填妥的 CHT Word／PDF 提案或同意書；不能推論其他位置也沒有。 | 確認身分證明、參賽同意書、作品提案規劃書及上傳回執。敏感文件不進 Git。 |
| 格式 | 尚無成品可檢查。 | A4，Word／PDF 擇一，有頁碼，字體至少 12pt，20MB 內，隊伍名稱作檔名；15 頁以內為建議，非硬性上限。 |
| 實體作品／影片 | 初賽不要求實體作品；影片選填。 | 功能未全做完不單獨造成送件失格，仍需如實區分成果與規劃。 |
| 既有作品限制 | AWS 參賽背景不等於 CHT 歷屆得獎排除條件；實際紀錄未知。 | 確認是否為 2022–2025 CHT 得獎作品，以及決賽前已合作上架／專案合作的情況。 |
| 原創、前團隊與第三方權利 | **待團隊確認**。程式存在與 Git 作者紀錄不能代替成果使用授權。 | 確認舊成員、素材、程式、資料與模型服務使用條件；有疑義由團隊向主辦查核。 |
| 決賽安排 | 官網列 10/16 入圍通知、10/31 決賽，現場簡報與 Demo 合計上限 12 分鐘；地點描述仍應以後續通知為準。 | 自備設備事先告知並取得主辦同意；未執行報名或聯絡主辦。 |

以上規則來源為[官方賽事頁的評選資料、時程與注意事項](https://cht5g.com.tw/index-smart.html)及[FAQ](https://cht5g.com.tw/)。本報告不估算得獎機率。

## 3. 專案快照、來源與範圍

### 實際讀取範圍

- 根目錄 `AGENTS.md`、`CLAUDE.md`、`README.md`、Agent Runtime 子目錄 `AGENTS.md`；`MASTER.md` 實際位於 `docs/design-system/MASTER.md`，不是根目錄產品主規格。
- 有效需求線索：Spec 02 **v1.3.2**、Spec 18、ADR 0014／0019、Wave 2 traceability；Persona v0.2 明記仍待訪談驗證。ADR 0016 的實作以 decision-support 呼叫鏈核對，未完整審查其所有目標功能。
- Core 的 Companion、ASR Gate、Memory policy／service／repository、事件／摘要、待辦、家屬報表、Elder authorization、Consent、Deletion 與 outbox 邊界。
- Runtime 的 orchestrator、Memory／Event extractor、SafetyEvaluator、production gate；Speech 的設定、provider router 與 Deepgram／Azure adapter 測試。
- 前端實際 voice turn／錄音介面、摘要頁、家屬報表路徑、public-asset service worker；本次沒有重新做 Browser 視覺驗收。
- Migration 檔名與相關 schema 演進：20260818 Memory trust／speaker／confirmation／decision support／legacy evidence，20260904 Care Action candidate，以及 20260915 B03／B04；未查目前遠端 DB schema，不執行 migration。
- `docs/project/` 的 Wave 2 Agent chain、Browser QA、B02、B03／B04、工作台及 branch closeout 紀錄；CI 依 SHA 核對。

### 本次執行環境

Core 隔離測試使用既存 `D:/Hackthon/kinsun-backend/services/core-api`，與主工作目錄同為 `acc84ef`，該 worktree 沒有根 `.env`；注入未使用的 dummy PostgreSQL DSN。未建立或切換 worktree／分支。Agent／Speech 使用主工作目錄既有 venv 與已檢查的 mock tests。

配置讀取只輸出列入允許清單的布林值、provider／model 名稱，以及 secret 是否存在，不輸出密鑰或 DSN。以新 Python process 載入主 checkout 的 Core `Settings()` 得到：

| 設定 | 結果與意義 |
| --- | --- |
| 原生驗證／App Session | 開啟；`FAKE_AUTH_ENABLED=false`。不代表目前已有可用展示帳號。 |
| `evidence_aware_memory`、`auto_low_risk_memory` | **false／false**。新增候選／確認與受控 Memory context 尚未在這份配置啟用。 |
| `asr_gate_enabled`、`speech_service_identity_enabled` | **false／false**。現有語音 UI 接線不能代替 Core Gate 啟用。 |
| assisted elder／care profile context | 均 false；不能將無帳號平板交接描述成已啟用展示。 |
| Core→Agent service identity | true。 |
| Runtime 根配置 | `MODEL_PROVIDER=gemini`，設定的 model ID 為 `gemini-3.6-flash`；`RAG_MODE=staging`、PostgreSQL backend、允許 needs-review citations；屬開發配置。 |
| Speech 服務配置 | 中文／英文 ASR 指向 Deepgram Nova-3；TTS 指向 Azure Speech，credential 欄位有值。本次未呼叫 provider，不能驗證帳號、額度、模型可用性或品質。 |

`Settings()` 載入出現一次 `.env` 第 3 行解析警告，但允許清單設定成功讀回；本次沒有輸出該行或修改它。需在 Demo 環境準備時處理。這些是**新 process 載入的配置結果**，不是對既有服務 process environment 的讀取。

對既有 runbook 約定埠執行唯讀 `/health`：8000 回 200；8001、8002、3000 未成功連線。只代表當時這四個 loopback endpoint 的狀態，不代表其他埠或外部部署不存在，也不能從 8000 health 確認其 commit／DB readiness。

### 未取得／未執行

未取得 S2 原始 `Kinsun.docx`，其構想僅依任務書摘要；S1 改讀官網 PDF。未讀私人身分證明、合約或主辦報名後台；未呼叫付費語音／LLM、真實通知、遠端 DB 寫入或隔離庫重建；未重啟服務、操作網路或重新啟用退場 QA campaign。未完成外部部署、硬體與真人場域驗證。

## 4. 功能證據矩陣

`STATIC_ONLY` 是程式查核；`MOCK_TESTED` 是既有隔離測試；歷史 `LOCAL_VERIFIED` 必須連同日期／版本／模擬資料範圍閱讀。表內不把歷史驗收改稱本次實測。

| 能力 | 實作狀態 | 驗證狀態 | 程式／契約證據（path、symbol） | 執行／測試證據 | 可宣稱範圍／缺口 |
| --- | --- | --- | --- | --- | --- |
| 語音錄製→ASR→Core Gate→Agent→TTS | IMPLEMENTED；啟用 PARTIAL | MOCK_TESTED；現場 E2E BLOCKED | `packages/frontend/src/lib/voice/canonical-voice-turn.ts:38` `transcribeTurn`、`:107` `speakTurn`；`VoiceInteractionPanel.tsx` `handlePress`；`services/core-api/app/services/companion_service.py` `_authorize_asr_input`；`services/speech-gateway/src/speech_gateway/app.py` | 本次 Speech 44、Core ASR／Companion 選測通過 | 有整段音訊流程與低信心確認。ASR Gate 配置關閉；未驗證現場收音、播放、完整耗時。`DEMO_BLOCKER`。 |
| 語言／provider | PARTIAL | MOCK_TESTED／真實 provider NOT_RUN | `services/speech-gateway/src/speech_gateway/settings.py:29`、`provider_router.py`；前端 `speech-gateway-client.ts` | Deepgram／Azure synthetic HTTP tests；設定有 key 不等於可用 | 中文／英文有 adapter；臺語／客語保留 SageMaker 路由，未確認有效 endpoint。混語未驗；英文 UI 不代表英文事件／Memory extraction，兩 extractor 均限制 zh。 |
| 文字陪伴與 Agent 邊界 | IMPLEMENTED（bounded slice） | MOCK_TESTED；歷史 LOCAL_VERIFIED | `services/core-api/app/services/companion_service.py` `run_turn`；`services/agent-runtime/src/agent_runtime/orchestration/orchestrator.py` `AgentOrchestrator.run` | 9/8 真實 Gemini chain；本次 Core／Agent 選測 | Gemini 產生回覆，Event／Action proposal 是 deterministic；Core 掌握正式狀態。不宣稱通用自主 Agent。 |
| Care Event 與 B03／B04 | IMPLEMENTED（本次切片） | MOCK_TESTED；歷史 LOCAL_VERIFIED | `services/core-api/app/api/care_events.py:262` `review_care_event`；`services/core-api/app/services/care_event_service.py` `review`；`schemas/care_event.py:63` | 9/16 真實登入 13 組流程；PR #51／#53，當前 CI 全綠 | 可修正類型／時間、篩選 MANUAL／CONVERSATION_SESSION／UNKNOWN，保存版本與稽核。UNKNOWN 不是感測來源。完整修正歷史導覽／正式事件重編仍未結案。 |
| 每日摘要 B02 | PARTIAL | MOCK_TESTED；當前 CI 的 DB job 成功 | `services/core-api/app/services/summary_service.py:52` `generate_from_verified_events`、`:291` `request_rebuild`；前端 elder detail `page.tsx:640` | 本次 summary unit；`tests/integration/test_summary_acceptance.py` 在 CI scope | 已覆核 current events、臺北日界、超過 32 明確拒絕、來源 IDs、STALE。尚無來源片段導覽及 rebuild UI；不宣稱自動重算已完成。 |
| Evidence／來源追溯 | PARTIAL | STATIC_ONLY；部分歷史 LOCAL_VERIFIED | `care_event_service.py` review before/after；`api/care_events.py` `_response`；`summary_service.py` source IDs | B03 真實版本／review／outbox；B02 報告 | 有事件／版本／opaque evidence reference，不等於可點回原始音訊或逐字片段；來源 API 應 bounded 且重驗授權。 |
| 分級 Memory Policy | PARTIAL（Core 基礎已實作） | MOCK_TESTED；啟用 BLOCKED | `services/core-api/app/policies/memory_policy.py:183` `evaluate_memory_candidate`；`memory_service.py:102` `create_candidate`、`:251` `confirm`；20260818 trust／confirmation migrations | 本次 policy、retrieval、service／promotion tests | LOW／MEDIUM／HIGH、版本／digest／Consent 機制存在；兩 rollout flags 關閉；語意 all-of 仍有靜態缺口，見第 6 節。不等於一般化可信自動記憶完成。 |
| Event／Memory 分流 | IMPLEMENTED（窄範圍）；通用能力 PARTIAL | MOCK_TESTED | `services/agent-runtime/src/agent_runtime/agents/memory_extractor/agent.py:23` `MemoryExtractorAgent.run`；Core `care_event_service.py:313` | 本次 `test_memory_extractor.py`、promotion tests | 只提取中文明確早餐習慣 DAILY_ROUTINE；VERIFY 後才嘗試建立 Memory 候選且重驗 gate，CORRECT 不直接 promotion。一次性餐食已有負例；任意否定／轉述／時間歧義未完整覆蓋。 |
| Speaker attribution | IMPLEMENTED（受控 Session 假設）；多人／裝置 PARTIAL | MOCK_TESTED | `memory_policy.py:126` `derive_turn_speaker_evidence`；`companion_service.py` `_speaker_evidence`；20260818 speaker migration | Elder-only gated voice／staff／missing evidence／expired consent 測試；真實聲紋 NOT_RUN | 已登入本人 text、或本人開啟的 gated voice Session 可形成 ownership；非 biometrics，沒有證明多人辨識。Device attribution 未找到。 |
| 覆核／關懷待辦 | IMPLEMENTED（self-assignment） | 歷史 LOCAL_VERIFIED；當前 CI | `care_action_candidate_service.py:133` `adopt`；`care_action_service.py:45` `create`、`:112` `transition`；`CareActionPanel.tsx` | 9/7 Browser、9/8 Gemini chain、9/15 工作台 real-auth | 有採用／拒絕／排除、來源版本、期限及狀態；未實作任意轉派，既有 synthetic accounts 已退場。 |
| 家屬邊界 | IMPLEMENTED 基本 gate；完整動態縮限 PARTIAL | STATIC_ONLY＋歷史 CI；本次隔離權限 tests | `api/reports.py:194`、`:212`；`report_service.py:185` `list_for_family`、`:219` `get_for_family`；tenant-scoped `report_repo.py` | 當前 CI 及本次 ElderAccess tests；未重演整條家屬發布鏈 | 查 PUBLISHED、active consent、指定收件關係及 actor。不是直接共享 Memory／逐字稿；read-side share scope 疑點見第 6 節。 |
| Consent 撤回 | IMPLEMENTED（已支援用途） | MOCK_TESTED；部分歷史 LOCAL_VERIFIED | `consent_service.py:64` `require_active`、`:299` `revoke`；`companion_service.py` requested outputs；`report_service.py` read gate | 本次 assisted consent／Memory gate／summary tests；歷史撤權 replay | 用途分開、基本語音撤回取消 Session、受控讀寫重驗；感測用途尚無實作，不能承諾 IoT 撤回／補送行為。 |
| 租戶／長者隔離 | IMPLEMENTED | MOCK_TESTED；歷史 LOCAL_VERIFIED | `authorization_service.py:35` `authorize_elder_with_decision`；`policies/elder_access.py`；tenant-scoped repositories | 本次 29 項權限／Consent／Memory repo 選測；真實 B03／B04 404 及工作台撤權 | 有 live scope、過期拒絕與隱藏資源存在性的控制；不是完整滲透測試。 |
| 更正／停用／刪除後不可再引用 | PARTIAL | MOCK_TESTED；歷史 CI | `memory_repo.py:176` `list_active_context_for_elder`；`memory_retrieval.py:57` `evaluate_memory_trust`；`deletion_service.py:187` | 本次 memory retrieval／repo；CI `test_deletion_workflow.py` | final gate 核對 current ACTIVE、Consent、版本、SYNCED projection；Core Memory 清除與 tombstone 有實作，其餘 deletion target 回 TARGET_NOT_CONFIGURED，不宣稱跨所有 store 已完整刪除。 |
| IoT 接入／裝置歸屬 | NOT_FOUND（搜尋範圍內） | NOT_RUN | `schemas/care_event.py` 現只接 MANUAL／CONVERSATION_SESSION；搜尋 app/src/config/scripts 的 sensor、device binding、MQTT／IoT | 無硬體／simulator 接入驗收 | 至少還需 source contract、device auth、綁定有效期間、用途同意、晚到資料與去重；`CLAIM_BLOCKER`。 |
| Evidence Fusion | DOCUMENT_ONLY／NOT_FOUND runtime | NOT_RUN | 任務書第 7 節；現行來源模型及搜尋結果 | 未找到獨立雙來源比較實作 | 不能把同一逐字稿衍生兩欄稱為 Fusion；路線 A 不作此宣稱。 |
| Personal Baseline | DOCUMENT_ONLY／NOT_FOUND runtime | NOT_RUN | Spec 02 US-K02；未找到個人基準計算服務 | 無歷史窗口／完整度／recompute 驗收 | 30/3 與 28/7 是不同構想；不得寫已建立個人健康基準或成效。 |
| Queue／同步 | server outbox IMPLEMENTED；edge queue NOT_FOUND | STATIC_ONLY／歷史 CI | `services/core-api/app/events/consumer.py` `IdempotentEventConsumer`；前端 `public/sw.js:1` | DB outbox／idempotency 測試；離線新增／重啟 NOT_RUN | server outbox 不等於 Sensor→Hub 離線 queue；SW 只 cache 兩項 public assets，不 cache BFF／navigation。 |
| 網路切換／離線 AI | NOT_FOUND | NOT_RUN | `VoiceInteractionPanel.tsx:90` online/offline 只切 UI 狀態 | 未操作網路 | 沒有自動 5G fallback、持久化補送或離線 ASR／LLM／TTS 證據。 |
| 部署／RAG production | PARTIAL；production BLOCKED | STATIC_ONLY／MOCK_TESTED | `services/agent-runtime/src/agent_runtime/app.py:43` empty production RAG allowlist；`:196` `validate_production_configuration`；ADR 0019 | 本次 26 production gate tests；當前 CI 10 jobs SUCCESS | 有 development RAG／Gemini 歷史 smoke，沒有核准 production runtime。不能靠切 APP_ENV 或解除 gate 冒充驗收。 |

## 5. 實際呼叫鏈與完成邊界

### 5.1 語音與文字

`VoiceInteractionPanel` → `transcribeTurn` → `issueVoiceTicket` → PCM JSON upload → Speech provider → Core ASR evidence → `runCompanionTurn` → Core `run_turn` → Runtime → reply＋synthesis capability → `speakTurn` → TTS／播放。

這是有實作的呼叫鏈；本次實際 provider 請求為零。低信心由 Core 決定，Browser 顯示待確認；逾時會取消 ASR，TTS 不可用可留下文字。這不代表一般失敗情境都有完整使用者提示，更不是 streaming 延遲數據。9/8 的 1818ms 是單一 Runtime adapter 觀測，不能代替麥克風→播放的 p50／p95。

### 5.2 事件、待辦與摘要

Core `run_turn` 重驗用途／scope → Runtime bounded proposal → Core session 完成／建立 NEEDS_REVIEW event → caregiver review command（live authorization、expected version、idempotency）→ immutable payload version、review、outbox → action candidate → 人工 adopt → formal action。

事件 CORRECT／EXCLUDE 會讓關聯摘要 STALE；`request_rebuild` 只要求重建，`generate_from_verified_events` 才重新產生。現有 UI 只顯示縮短來源 ID；無完整來源片段點擊與重建閉環。

### 5.3 Memory

目前 extractor 只產生特定中文早餐習慣 → 私有 Event version proposal → 人工 VERIFY → Core 再驗 Memory gate／Consent／source match／policy → 符合條件的候選 → 本人固定版本確認 → ACTIVE → `MemoryRepository.list_active_context_for_elder` 再驗權威 Memory、Consent、confirmation record、digest 與同步投影，才送 Runtime。

這條路徑仍有 rollout、projection 及 Demo 依賴。不得只在 SQL 填 ACTIVE 或沿用 legacy Memory，就宣稱下次對話能可信引用。後端 LOW branch 存在，但目前 extractor 不產生 MUSIC_PREFERENCE／HOBBY／PREFERRED_ADDRESS；一般偏好自動保存不在已接通 slice。

## 6. 規格、實作與安全疑點

| 問題 | 分類／證據 | 影響與處置建議 |
| --- | --- | --- |
| 舊文件說 Memory risk／speaker／version binding 尚未實作 | **過期進度敘述**：AGENTS／Spec 18 的 current paragraph 與 20260818 migration、現行 policy／service／tests 不一致 | 保留 Spec 18 的產品要求；完成狀態改依程式與本報告。不把「已有基礎」擴大為 Target 全完成。本次未修改協作文件。 |
| LOW all-of 的第一人稱、否定、轉述、時間歧義 | **有效規格尚未完整落實的靜態缺口**：Spec 18 §7.2／MEM-P04；`evaluate_memory_candidate` 依 normalized content／question、敏感詞、kind、confidence、speaker、conflict 決策，沒有直接檢查原句第一人稱／否定／時間；早餐 extractor 使用 regex search | `CLAIM_BLOCKER`；若要啟用一般化自動 LOW，升為該 rollout 的 `SAFETY_BLOCKER`。目前 flags off、bounded MEDIUM extractor／人工確認降低影響；本次沒有注入或寫入反例，不能聲稱已重現自動保存漏洞。 |
| 家屬報表 read-side share scope 重驗 | **靜態安全疑點**：`ReportService._validate_recipient_scope` 發布時檢查 REPORT_SCOPE，但 `list_for_family` 讀取時只比較 active relationship／consent ID，未按 report type 再比 `share_scope`；通用 Elder authorization 檢查 `care_relationship.scope`，不是 `family_relationship.share_scope` | 需要現有關係縮限報表類型後的 HTTP／DB 負例；本次未重現，不能判所有家屬讀取安全通過。對承諾即時縮限分享的真實資料展示，列待解除 `SAFETY_BLOCKER`。撤銷／到期整條關係的拒絕，不可代替細粒度縮限驗收。 |
| 把本人 Session 當聲紋 | **宣稱不符**：`derive_turn_speaker_evidence` 明示 Elder-only Session 信任假設，Spec 18 §3.4 允許受控 Session 方案 | 可寫受控 Session ownership；不可寫已完成人聲生物辨識、辨識陌生人或多人分離。 |
| 覆核完成即完整 Evidence-first | **未完成體驗**：B03 有 before/after 稽核；B02 仍只有來源 IDs，來源 snippet、完整修正歷史與 rebuild UI 未完成 | metadata 可追溯的宣稱保留，原始證據一鍵回查降級。來源 API 需重新驗權、版本與最小內容，不能直接公開音檔／逐字稿 URL。 |
| 兩來源條件與直接陳述混用 | **待設計擴充**：Spec 02 US-K02 的推估訊號要求不等於 Care Event 直接陳述；未找到 Fusion runtime | 保留直接陳述事件；路線 B 需定義 observational source，不能刪掉推估訊號的雙來源條件。 |
| Baseline 30/3 對 28/7 | **不同設計、未落地** | 由指標／用途定義版本化 policy 再實作，不任選數字宣稱已分析。 |
| 全資料刪除與 projection／外部系統 | **部分實作**：Deletion processor 只處理 Core Memory target；其他 target 明確失敗 | 不宣稱所有 object/index/cache/queue 已清除。啟用外部 projection／IoT 前補撤回、tombstone、補送抑制與 recovery。 |
| AWS 部署圖／AURORA 字串 | **歷史命名／架構已退役**：ADR 0019；Deletion 的 AURORA target 字串仍對應目前 SQLAlchemy Core 處理 | 不推論目前使用 Aurora／Neptune／AWS IaC。Hub 正式資料 authority 維持 Core；未因比賽另開平台。 |
| 無帳號長者展示 | **未啟用、用途刻意限縮**：assisted session flags off；現有設計只允許 BASIC_VOICE | 不用照服員啟動 Session 代替長者的 Memory／event consent。 |

本次沒有進行完整資安或法律稽核；沒有新測試重現的疑點與已通過既有測試分開呈現，不把未測情境寫成已確認漏洞。

## 7. 本次測試紀錄與歷史證據

### 7.1 本次確實執行：200 項既有隔離測試通過

共同日期／版本：2026-09-16，`acc84ef`。下列未呼叫付費 provider 或 shared Supabase。`python` 均為對應服務既有 `.venv/Scripts/python.exe`；沒有安裝依賴或新增測試。

| ID | 目錄／命令 | 結果 | Mock／限制 |
| --- | --- | --- | --- |
| R1 | `kinsun-backend/services/core-api`：`python -m pytest tests/unit/test_memory_policy.py tests/unit/test_memory_retrieval_policy.py tests/unit/test_memory_service.py tests/unit/test_care_event_memory_policy.py tests/unit/test_care_event_memory_promotion.py tests/unit/test_asr_gate_service.py tests/unit/test_asr_gate_agent_input.py tests/unit/test_companion_service.py tests/unit/test_summary_generation.py tests/unit/test_care_event_api.py -q` | **82 passed**，3.72s | dummy DATABASE_URL，mock repository／Session／Runtime；不是 PostgreSQL E2E。 |
| R2 | 同上：`python -m pytest tests/unit/test_elder_access_policy.py tests/unit/test_assisted_consent_acknowledgement.py tests/unit/test_memory_repo.py -q` | **29 passed**，1.43s | 權限與查詢組裝／scope 的隔離測試。 |
| R3 | `kinsun.ai/services/agent-runtime`：`python -m pytest tests/unit/test_memory_extractor.py tests/unit/test_confirmed_memory_context.py -q` | **8 passed**，5.72s | synthetic request，deterministic extraction／context；`APP_ENV=test`、`MODEL_PROVIDER=mock`。 |
| R4 | 同上：`python -m pytest tests/unit/test_production_configuration.py -q` | **26 passed**，3.58s | `RAG_MODE=disabled`；證明 production 阻擋條件，非 deployment 成功。 |
| R5 | 同上：`python -m pytest tests/unit/test_provider_and_contract.py -q` | **11 passed**，0.44s | mock provider、contract、特定中文醫療高風險規則；不是完整 adversarial evaluation。 |
| R6 | `kinsun.ai/services/speech-gateway`：`python -m pytest tests/test_deepgram_asr.py tests/test_azure_tts.py tests/test_core_voice_gate.py -q` | **44 passed**，1.69s | 合成 PCM／文字、HTTP MockTransport，process 注入 synthetic provider keys；非真實語音辨識或音質驗收。 |
| R7 | 新 process `Settings()` 的允許清單輸出；urllib GET 約定 localhost `/health` | 配置成功讀取；8000 200；其餘三埠未連線 | 無資料寫入；有 dotenv parse warning，見第 3 節。health 不證明版本／DB／provider。 |

沒有重跑全部 frontend build／suite 或所有昂貴 CI。當前 commit 的合併後 [CI 35068801419](https://github.com/71bk/kinsun.ai-product/actions/runs/35068801419) 已查核為 **10 jobs SUCCESS**（2026-09-16 07:29:40 UTC 建立，head=`acc84ef`），包含 core-db、contracts、cross-service、frontend。這是既有 CI 證據，不是本次 local execution。

### 7.2 歷史證據的可用範圍

| ID | 日期／基準／報告 | 可證明 | 不可延伸 |
| --- | --- | --- | --- |
| H1 | 9/8，PR #31 `c3d9138` 起，修正後 PR #32 `e94f0f8` CI／`84ef958` main；[Agent chain](../../project/wave2-agent-chain-qa-20260908.md)及 [traceability](../../../.kiro/specs/wave-2-caregiver-loop/traceability.md) | 真實帳密、BFF→Core→Gemini→Supabase，合成文字、人工 VERIFY／adopt，replay／expiry | 非麥克風、ASR／TTS、RAG、完整新版本重演；帳號臨時授權已退場。 |
| H2 | 9/16，PR #51，main `6bf89a8`；前端 build `6b5448e`；[B03/B04 real-auth](../../project/b03-b04-real-auth-20260916.md) | 修正、來源篩選、409、404、DB version/review/outbox；六筆合成事件 | 非真實長者、硬體或新 Agent 提案；campaign 已永久退場。本次未重用。 |
| H3 | 9/15，[home-care workbench real-auth](../../project/home-care-workbench-real-auth-20260915.md)；版本以原報告為準 | 真實登入、服務開始／完成、交班／待辦與跨 worker 邊界 | 不代表語音與家屬報告完整串接。 |
| H4 | 9/16，[B02 acceptance](../../project/b02-summary-acceptance-20260916.md)，PR #52 merged `38047f6` | 上限拒絕、Consent 先檢查、ORM update、DB regression；後續當前 CI 成功 | 報告早期「DB pending」為歷史階段；source snippet／rebuild UI 仍未交付。 |
| H5 | 9/16，[branch closeout](../../project/branch-closeout-20260916.md)，PR #53 | 610 frontend tests、build/typecheck/lint、16 張登入頁截圖檢查 | 非本次重跑，非完整產品可用性、語音或真人測試。 |

### 7.3 任務書 T01–T18

PASS 僅指表列範圍；同列尚未覆蓋部分明記，不能合併成完整 E2E 通過。

| ID | 結果 | 本次／歷史證據與剩餘限制 |
| --- | --- | --- |
| T01 真實語音一輪 | **BLOCKED** | 配置 ASR gate off、約定 Speech／Agent 未回應；adapter tests 不能代替真實錄音。 |
| T02 否定／人物／時間／低信心 | **NOT_RUN（完整語意案例）** | R1 的 ASR gate tests PASS；第一人稱／轉述／時間歧義完整否定集未執行，Memory 靜態缺口見第 6 節。 |
| T03 有語音陳述、無 sensor | **PASS（文字陳述切片）** | H1 無感測即可提案；真實語音版本 NOT_RUN。 |
| T04 來源不一致 | **N/A（路線 A）** | 路線 A 不宣稱 Fusion；採 B 時必做，屆時非 N/A。 |
| T05 UNKNOWN／MULTIPLE／裝置不明 | **PASS（已實作的 UNKNOWN speaker gate）** | R1 阻擋 unverified／staff voice；實際多人辨識及裝置歸屬 NOT_RUN。 |
| T06 低中高 Memory policy | **PASS（R1 的既有案例）** | 分級、HIGH 拒絕、MEDIUM version／digest 通過；LOW 完整 all-of 與 live rollout 尚未驗收。 |
| T07 一次性與穩定作息 | **PASS（有限早餐案例）** | R3：單日早餐不提 Memory、每日早餐提 DAILY_ROUTINE。任意語句不可類推。 |
| T08 修正／排除／失效／待辦 | **PASS（H1/H2 的切片與 CI）** | B03 audit、候選採用與摘要 STALE；自動重算／所有下游一致性 NOT_RUN。 |
| T09 家屬直接越權 API／工具 | **NOT_RUN（完整家屬矩陣）** | R2 的 Elder scope tests 通過、報表 gate 靜態存在；報表類型縮限、下載／檢索全矩陣未驗。 |
| T10 撤回用途 | **PASS（R1/R2 已支援用途）** | Memory／基本語音／summary consent 邊界；感測／Fusion 撤回未實作。 |
| T11 裝置缺值／不足 | **N/A（路線 A）** | 無 Sensor／Baseline 承諾；不能把沒有資料顯示成穩定。 |
| T12 離線新增／恢復重送 | **N/A（路線 A）** | server idempotency 不替代 Hub 測試；B/C 若承諾離線則必做。 |
| T13 queue 重啟保全 | **N/A（路線 A）** | 未宣稱 edge persistence。 |
| T14 撤回／刪除／重綁後補送 | **N/A（路線 A 的裝置補送）** | Core 撤回／replay 仍適用並有其他測試；不能以此略過既有隱私風險。 |
| T15 provider／DB 失敗 | **PASS（R1/R5/R6 與既有 CI cases）** | synthetic failure／fallback；真實 provider outage、部署恢復未驗。 |
| T16 記憶失效後再次對話 | **PASS（R1/R2 final retrieval gate）** | legacy、stale、digest、rollout 拒絕；真人連續兩回合與跨外部 store 清除 NOT_RUN。 |
| T17 醫療誘導／prompt injection | **PASS（R5 特定醫療案例）** | prompt/context 邊界有程式；完整 injection、多語與改寫攻擊集 NOT_RUN，不能宣稱完全防護。 |
| T18 重複主 Demo | **NOT_RUN** | 尚無當前完整劇本多次重演成功率。 |

## 8. 初賽提案材料與商業判斷

| 七項必要內容 | 可延用材料 | 缺口 |
| --- | --- | --- |
| 1. 作品主題 | Spec 01／01A、現有多角色 workflow | 由團隊確認首個場域；建議沿日照情境，勿同時宣稱多場域已落地。 |
| 2. 作品特色 | Core authority、來源版本、人工覆核、待辦、分項 Consent | Memory／IoT／韌性依第 9 節降級；不以 feature 數量代替差異。 |
| 3. 設計理念 | Spec 07／18、ADR 0014、Elder access 與 safe fallback | 補白話描述誰能看什麼、無同意時如何繼續基本陪伴。 |
| 4. 使用情境 | H1/H2/H3 的可核對切片、Persona | 整理一條 12 分鐘內劇本，明示合成資料、文字／語音與失敗路徑。 |
| 5. 商業模式 | 有產品假設與角色背景 | 未找到直接訪談／試用／採購意向、可核對成本表或 CHT 合作證據。 |
| 6. 預期成果 | 現有測試／驗收可作技術基線 | 整理時間、覆核負擔、每人候選數、排除率、誤歸屬、Demo 成功率需訂量測計畫；不能編實績。 |
| 7. 工具與其他 | Next.js／Core／Runtime／Speech／Supabase、CI、ADR 0019 | 用現行 provider-neutral 架構；補人力、環境、secret injection、未啟用依賴。 |

`docs/spec/01A...v0.2.md` §研究狀態明說 Persona 來自公開情境與團隊假設，仍待訪談。搜尋 `docs/project`／`docs/spec`／`docs/runbooks` 的訪談、試用、意向、採購、月租與 CHT 相關內容，未找到能支撐「需求已驗證／已降低成本」的直接成果檔；不代表團隊在工作區之外沒有資料。

**建議商業假設，尚未驗證**：日照機構為買方，照護員為每日覆核者，長者與家屬為受益者；先驗證交班整理／找來源／家屬溝通是否省時，以及增加的覆核時間是否抵銷效益。成本先列 ASR 分鐘、TTS 字元／用量、LLM tokens、DB／運算、維運及機構覆核人力，待用量與單價證據齊備再估價。本次不捏造定價、ROI 或醫療成效。

CHT 連結可規劃為機構連線／行動備援、未來裝置與連線管理、場域通路合作；目前都只能標「規劃／待驗證」，沒有帳號、平台 API 或正式合作證據。單純走行動網路不等於整合 IoT 平台，亦不保證海地星空獎資格。

官方初賽商業與市場、業務連結合計有相當比重；決賽商業與市場與技術成熟度同等重要。應補買方與實際使用證據，不把全數時間投入新功能。評分依[官方評分表](https://cht5g.com.tw/index-smart.html)，本報告不給虛構官方分數。

## 9. 提案宣稱清單

| 擬使用文案 | 判斷 | 建議文案 |
| --- | --- | --- |
| 已實作照護者覆核與待辦 | **可保留，標範圍** | 已在本機以合成資料、真實帳密與 API／DB 完成事件覆核、候選採用及自我指派待辦驗收。 |
| 已實作可追溯證據 | **需限定** | 保存事件來源、版本、修正與處理者稽核；原始片段導覽仍在補齊。 |
| 已完成智慧長期記憶 | **需降級** | Core 已有風險分級、同意與固定版本確認機制；目前記憶擷取為有限情境，啟用與端到端展示尚待驗證。 |
| 所有記憶均逐筆人工確認 | **須修正** | 目標政策依風險分級；MEDIUM 需本人固定版本確認，LOW all-of 自動保存仍有啟用與完整語意驗收條件。 |
| 已辨識每位說話者 | **須移除** | 採受控本人 Session 與 ASR Gate 的 ownership 假設；未宣稱聲紋或多人辨識。 |
| 已支援中英臺客與混語語音 | **需降級** | 有分語言 provider 邊界；中文／英文 adapter 測試通過，真實語音、多語品質及臺客部署待驗證。 |
| 已整合實體感測／Fusion／個人基準 | **須改列未來規劃** | 評估單一感測來源與既有 Core 工作流整合，裝置與 API 未確認。尚無 simulator 接入證據，也不可寫成 simulator 已驗證。 |
| 斷線自動切到 5G、離線仍可 AI 對話 | **須移除** | 第一版依賴網路；離線持久化與網路備援為後續評估。未做手動切換測試，也不宣稱手動恢復已驗證。 |
| 已降低照護人力成本 | **須改為目標** | 預計量測整理與覆核時間、候選數與誤判成本，驗證是否改善工作負擔。 |
| 已正式部署／可正式營運 | **須移除** | 已有本機／CI 技術驗證；production retrieval、部署與場域驗收未完成。 |
| 已與中華電信合作 | **須保留未知** | 規劃與中華電信相關連線、管理或通路服務整合，尚待帳號、介面及合作確認。 |

## 10. 最小補齊與時程建議

以下是規劃估算，不是既有承諾。**假設一位熟悉現有 codebase 的開發者全時投入，文件與商務由團隊同步處理**；人力尚未知，外部審核／API 開通等待時間不含在工程人日。工作可有重疊，不能把區間直接當保證交付日。

| 優先級／建議窗口 | 目標、延用模組及邊界 | 依賴與驗收 | 工作量／縮減方案 |
| --- | --- | --- | --- |
| **Submission P0：9/16–9/18 中午前** | 確認資格／權利、完成七項提案與上傳；延用本報告、Persona、H1/H2 的證據，不改產品 | 團隊回覆、官方模板；逐項文件檢核與回執 | 約 0.5–1.5 人日；影片選填。未確定的 IoT／效果移至後續，不用趕做硬體代替文件。 |
| **Demo P0：9/19 起先收斂** | 修正並固定開發／展示配置、處理 dotenv warning；用既有 Core／Runtime／Frontend／Speech runbook 啟動新的隔離合成劇本 | 新 synthetic 短效授權、provider 可用、ASR／service identity 安全設定；至少三次完整成功，記錄失敗與耗時 | 約 2–4 工程人日，不含外部等待。語音無法完成就降為文字演示並明示狀態，不假裝現場語音。 |
| **Demo P0：安全與 Memory 決策** | 先確認是否展示 Memory；延用 `memory_policy`、extractor、service／retrieval gate，補第 6 節 all-of 與 share scope 負例／修正 | 人工 reviewer／Elder confirmation、schema／projection readiness、Consent；拒絕否定／轉述誤歸屬，縮限 scope 後 fresh GET 拒絕 | 約 2–5 工程人日；無法解除時不啟用自動 LOW，以有限且確認過的記憶切片或規劃說明呈現；家屬疑點未解不使用真實敏感資料。 |
| **Demo P0：Evidence 與摘要閉環** | 延用 `care_events.py`、`summary_service.py`、elder detail UI；新增 bounded source snippet 需先定 contract，再接明確 rebuild／generate | 同 elder／tenant／版本授權；修正後 stale 清楚、顯式再產生、32/33 邊界、失權清除、真實登入 Browser 驗收 | 約 2–4 工程人日；縮減為清楚展示來源 ID／版本與已有覆核，不宣稱一鍵原文與自動重算。 |
| **Demo P0：買方／UX／成本** | 延用 Persona 問題清單、現有照護工作台；訪談與定時任務試用，取得可公開的去識別證據 | 場域同意、照護者時間；記錄基線、覆核新增負擔、樣本與限制 | 約 1–3 人日＋排訪等待；無樣本就呈現假設及驗證計畫。 |
| **Demo P1：單一 Sensor（另行決策）** | 沿 Core 接入契約／來源模型／人工 review／idempotency，增加 source attribution 與 observations；不是另建正式資料系統 | 可用硬體或明示 simulator、device credential、歷史綁定、用途 consent、缺值／重送／晚到／撤回驗收 | 介面穩定前提下約 5–10 工程人日；沒有硬體就僅承諾軟體接入測試；本次未授權實作。 |
| **Demo P1：Baseline／離線持久化** | 必須在單一來源契約穩定後再做；版本化窗口、品質與排除規則、local queue、ACK／重試、撤回抑制 | 離線期間新增資料、Hub 重啟、恢復僅一次處理；資料不足不得當零；測試條件由團隊確認 | 約 5–10 工程人日以上；硬體／網路不確定時不納入 10/31 核心承諾。 |
| **P2：賽後或另立計畫** | 多裝置、衛星、自動網路切換、完整 production IaC／治理 release、ERP 擴充 | Owner／provider／場域決策 | 不提供缺乏依據的估期；不影響此輪初賽提案。 |

建議在入圍通知前完成路線 A 的反例與重演；入圍後至 10/31 集中於 12 分鐘腳本、展示環境復原及證據整理。若同時承諾一般化 Memory、Sensor、Baseline、離線與自動切換，在未知人力下應評為 HIGH_RISK，而非以 CI 綠燈推估可以全部完成。

## 11. 最少待團隊確認事項

1. 組別、人數、代表人／國籍／年齡／排除身分，及是否已完成必繳文件與上傳。
2. 舊 AWS 團隊成果的參賽使用權、CHT 歷屆得獎與既有合作限制是否涉及本作品。
3. 第一個實際買方／場域、可取得的訪談或試用證據，以及到 10/31 可投入的人力。
4. 是否真的已有一種可取得資料的設備／API，以及能使用哪些 CHT 服務；若沒有，採路線 A。

本次已先向使用者提出第 1／2 類問題；截至報告寫入時未收到回答，故行政狀態保留未知。以上不需要提供身分證號、密碼或 API key。

## 12. 審查交付邊界

本報告新增於指定路徑；沒有更改產品碼、測試碼、migration、鎖檔、秘密或資料。既有 QA campaign 未復活，沒有登錄報名、發通知、使用真實個案或部署。測試與靜態查核已足以支持「主題適合、初賽有條件可送、路線 A 優先」；尚不足以支持「所有準備已完成」或「正式環境可營運」。
