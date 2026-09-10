# 長照法 RAG 治理同步：唯讀預覽與修復計畫

- 日期：2026-09-09
- 狀態：`STAGING_SYNC_VERIFIED / LOCAL_AGENT_ACTIVE / BROWSER_RAG_QA_PASSED`
- 範圍：公開法規來源 `moj_long_term_care_services_act_20210609` 的 71 筆 ordinary runtime candidates。
- 最新授權：2026-09-10 使用者確認開發資料庫同步與本機 Agent 切換；見獨立授權與第 8 節。
- 逐筆證據：[同步預覽 JSON](rag-law-governance-sync-preview-20260909.json)。此檔不是可直接執行的 apply manifest。

## 1. 需求與驗收邊界

| 面向 | 本次定義 |
| --- | --- |
| Persona / Story | 長者查詢「長照法」或「長照法第二條」，取得受治理的公開知識與可核對引用 |
| 本次 AC | 列出確切候選、原值、假設修正值、核准依據、完整性檢查及仍須封鎖資料；DB 零寫入 |
| Domain State | 不觸及 `eldercare_ai`、Consent、Event、Memory 或正式照護狀態 |
| Security Gate | current / stop / risk / purpose / audience / review / production / bytes integrity 繼續 fail closed |
| Test Gate | 唯讀快照與 checksum 比對；修復後的 live retrieval、精確條文與安全負例另行驗收 |

## 2. 已確認原因

現行 release 為 `rag-v2-v002-bab68588963b`，embedding profile 為
`ep-google-00a12ec45096fa9d97d9e9b6`，runtime policy 為 v003。

Core 會將「長照法」路由至 `legal_reference`，Agent 將別名展開為「長期照顧服務法」。
先前本次排查的兩次直接檢索，均取得 2 筆搜尋結果、0 筆合格回覆引用，最後 `NO_DATA`。
這不是初始化失敗，也不等於資料庫沒有法規。

資料庫的 71 筆 ordinary 法規候選均存在，但有下列狀態：

| 欄位 | 遠端原值 | 假設經外部同步核准後的目標 |
| --- | --- | --- |
| `requires_professional_assessment` column 與 retrieval-policy JSON | `null` | `true` |
| `retrieval_block_reasons` | 僅 `requires_professional_assessment_missing` | 移除這個已解決原因；其他原因不得順便移除 |
| `retrieval_eligible` column 與 retrieval-policy JSON | `false` | 全部剩餘 gate 通過才為 `true` |
| `review_status` | `needs_review` | 本次最小修復範圍維持原值 |
| `production_approved` | `false` | 維持 `false` |

本機 policy 已將這 71 筆 assessment 補為 true，但
[PostgreSQL 搜尋](../../services/agent-runtime/src/agent_runtime/rag/postgres_backend.py)
在搜尋前要求 live `retrieval_eligible=true` 且 block reasons 為空；policy 不可覆蓋這個撤銷邊界。
`951498e7` 於 2026-09-03 加入此 live gate，早於該變更的成功 smoke 不能作為目前可用證據。

因此，單改 query、排序、降低分數門檻或重啟服務，都不能解除這個資料治理前置封鎖。

## 3. 唯讀預覽結果

| 檢查 | 結果 |
| --- | --- |
| 本來源遠端 rows | 72 |
| ordinary policy 候選 | 71 |
| 71 筆文字實算 SHA / column SHA / policy SHA | 全部相符 |
| 71 筆 embedding-text 實算 SHA / column SHA / policy SHA / embedding row SHA | 全部相符 |
| 71 筆 v002 canonical record SHA 與遠端 record SHA | 全部相符 |
| 71 筆 column / JSON 的 assessment 與 eligibility 一致性 | 全部相符 |
| 本機 v002 checksum inventory | 29 檔，0 不符；inventory digest 與遠端 release 相符 |
| 本機 v003 checksum inventory | 24 檔，0 不符；inventory / crosswalk digest 與 policy binding 相符 |
| assessment acceptance digest / runtime policy pin | 相符 |
| 假設只解決已核准 assessment 缺失，且 snapshot 狀態未變 | 71 筆可通過所檢查的 live eligibility 條件 |
| 本次 DB 寫入 | 0 |

第二條確實存在：prior chunk ID 結尾 `_0002`，locator 為「第 1 頁／第一章 總則／第 2 條」，
與上述 71 筆具有相同 blocker，並非漏匯第二條。

另一筆 `_0048`（第 44 條）不在這 71 筆 pool：`high_red_line`、`stop_normal_rag=true`，
其三個 block reasons 與原欄位全部保留。本預覽不授權解除它的 assessment 缺失或任何其他封鎖。

### 方法與限制

- 檢查採固定 SELECT 與 release / profile / source bound parameters；沒有 INSERT、UPDATE、DELETE 或 DDL。
- 最終快照在 repeatable-read 交易內顯式執行 `SET TRANSACTION READ ONLY`，並確認
  `SHOW transaction_read_only = on`。先前診斷雖僅執行 SELECT，但觀察到 transaction 為 off，
  所以不能只依 engine 的預設連線參數宣稱交易已強制唯讀。
- 原始文字只在記憶體中算 hash；報告不保存正文、query vector、憑證、DSN 或私人照護資料。
- 只核對上述法規列；未重驗全部 726 筆 embedding 向量值或 fingerprint。
- 此處「可通過 live gate」是靜態差異預覽，不是同步後 recall、引用數量或回答品質的測試結果。
- 未重新核對官方網站法規時效；本報告不提供或確認任何現行法條解釋。

## 4. 核准依據與授權缺口

核准依據為
[Owner assessment acceptance v004](../../data/rag-v3/review/acceptance/v004/owner-assessment-response-policy-acceptance.json)，
SHA-256 `dcc923a3910e556c535a26856644fabc097a78b36e2a2492409ee987ce106c69`。
其 scope 是 `ORDINARY_RUNTIME_CANDIDATES_ONLY`，null → true，回覆必須附 deterministic advisory。
其 `gates.external_sync` 明確為 `NOT_AUTHORIZED`，`production_approved=false`。

因此，既有核准證明本機 assessment policy 的依據，不等於核准更動遠端 release。
本次「開始」承接唯讀預覽與計畫，也不把外部同步授權缺口自動解除。

## 5. 建議修復順序（A 的本機候選與 runtime 相容性已完成，其餘見第 7 節）

### A. 本機建立可審查的新版本同步工具與候選

1. 以本快照的 release / profile / 71 個精確 IDs / authority digest 定義 scope；重新讀取時
   有額外 blocker、停止／版本變更或 hash 不符就拒絕，不套用舊預覽。
2. 優先設計 immutable successor release，保留舊 release 完整可回復；不要直接更新舊 row 卻保留
   舊 `record_sha256` / candidate inventory。[既有 importer](../../services/core-api/app/rag_projection_importer.py)
   以 immutable candidate 驗證 release 與 record hashes，並不提供一般 UPDATE 同步功能。
3. 新版本只改 71 筆的上述治理欄位；其他 655 筆不提升權限、不移除 blocker。
   新 release 的完整 projection、record hashes、checksum manifest 與 lineage 必須一致。
   不可只插入 71 筆，卻沿用舊 release 的 726 筆計數或完成 receipt。
4. 現有 loader / importer / runtime policy 對版本、prior IDs、source release 與固定 554 筆 pool
   有綁定。先驗證新 release 的 ID 對照與 schema 相容性；必要時新增支援及 policy / audit successor，
   不改寫已封存的 v002 / v003 或歷史 audit bytes，也不只修改環境變數碰運氣。
5. embedding 只在 profile、dimension、task type、embedding-text hash 與向量完整性驗證通過後重用；
   71 筆本次文字相同不等於已驗證整個 successor 的 726 筆。無證據不重用，也不默默付費重建。
6. 本機 dry-run 工具須預設不寫入，輸出完整 before / after digest 與剩餘 gate；
   apply 工具另需明確 approval / manifest digest / exact target，不能讓此預覽 JSON 直接變成 apply 權限。

### B. Owner 明確核准後才建立及啟用 staging release

1. 核准範圍須包括目標環境、新 release、精確差異 manifest、寫入 principal、啟用與回復步驟。
2. DB apply 使用明確 scoped writer、單一交易與一致性檢查，建立 truthful ingestion receipts；
   任一缺筆、hash 不符、狀態漂移或並行撤銷即 rollback。Agent 保持 read-only reader，勿擴大其 grants。
3. 啟用前再次核對目前撤銷／stop／current 狀態，避免複製舊快照造成被撤回資料復活。
4. 先對新 release 做受控 staging smoke，通過才切換成匹配的 release + policy + embedding profile，
   再重啟經確認的目標 Agent。舊 release 不刪除。
5. 回復須保存舊設定與新版本 receipt；只有舊 release 仍符合當時最新安全狀態才可切回。
   若有後續撤銷而無法安全切回，停止 retrieval 並維持 no-guess fallback，不能復活舊內容。

### C. 上線前與回歸驗收

- 「長照法」：受治理法規引用、mandatory assessment advisory、production flag 仍為 false。
- 「長照法第二條」／「長照法第2條」：必須包含精確第二條且回答有來源支持；有任意 3 筆引用不算通過。
- Elder / Family / Care Professional：各自經正確 purpose / audience gate；非允許用途拒絕。
- `_0048` 高風險／stop、非 current、額外 blocker、錯誤 hash、缺失 metadata：仍不可進 context。
- apply idempotency、錯誤 release / profile / approval digest、並行撤銷、半途失敗與安全 rollback。
- provider timeout / retrieval unavailable / NO_DATA 維持固定 fallback；不把錯誤或正文放一般 log。
- 最終以 synthetic 登入帳號經 Browser/BFF → Core → Agent → DB 完整測試，不能僅以直接 Retriever 成功宣稱實機完成。

目前至少 3 筆引用的門檻不在本修復自動調整範圍。同步後若精確條文只有 1–2 筆合格證據，
另列 evidence-sufficiency 設計與契約／安全評估，不湊不相關資料，也不直接降低門檻。

## 6. 下一個可執行工作與未完成項目

已新增 [本機離線預覽工具](../../scripts/rag/preview_law_governance_sync.py)，只使用標準函式庫：

```powershell
uv run --frozen --project services/core-api python scripts/rag/preview_law_governance_sync.py
```

- 只讀本機 pinned v002 inventory、runtime policy v003、assessment acceptance v004；
  不讀 `.env`、不建立 DB／provider client，不支援 `--apply`、輸出檔案或 pin override。
- 以純函式在記憶體預覽 71 筆 retrieval policy 三個欄位差異，其他 655 筆 record digest 不變。
  輸出逐筆 before / hypothetical policy 與 record hashes、完整集合 digest 和 input inventory。
- stdout 的 `OFFLINE_DELTA_NOT_A_RELEASE_OR_APPLY_MANIFEST` 不是新 Chunk contract：
  假設資料保留舊 IDs 僅供差異比對，不可交给 importer；未生成新版本或啟用權限。
- 缺筆／重複 ID／SHA 不符／额外 blocker／停止／過期來源狀態／review 漂移／核准 scope 不符會失敗，
  不產生部分成功報告；一般例外不输出輸入值。偵測到本機輸入變動需重新執行。
- 每次重跑會重新驗證本機 artifact；**不檢查 live DB 漂移、遠端 embedding 向量或查詢排名**。
  它不可取代第 3 節的遠端快照，也不能取代未來 apply 前的 live 檢查。

[離線測試](../../services/core-api/tests/unit/test_law_governance_preview.py)與既有 projection importer
unit regression 共 47 passed、0 failed；collection 與執行前後的輸入雜湊一致。
精確命令、時間、收集 node digest、stdout log SHA-256 與輸入清單見
[驗證紀錄](rag-law-governance-offline-validation-20260909.json)。Ruff lint / format 通過。
既有 CI 的 `scripts/rag/` 規則已包含 Core unit 與 RAG jobs，不需新增 workflow。

上述 47 個測試及 JSON 驗證紀錄只涵蓋最初離線預覽階段，不涵蓋下列後續實作。

## 7. 本機 successor 進度（2026-09-10 更新）

依公開知識處理技能保留舊版本；沒有覆寫歷史 sealed artifact，也沒有同步外部資料。

| 本機產物 | 已完成內容 |
| --- | --- |
| `data/rag-v2/candidates/v004/` | 17 sources、726 chunks；完整新 ID 對照、schema、checksum 與 lineage。僅 71 筆提升上述治理欄位，其他 655 筆限制不變；所有文字與引用內容維持原值 |
| `data/rag-v3/governance/source-family-policy/runtime/candidates/v004/` | 包裝原 v003 policy；554 筆 pool 不擴大，綁定新 release / profile，錯誤綁定拒絕初始化 |
| `data/rag-v3/governance/source-family-policy/audits/v009/preflight/` | 新程式與候選的本機治理稽核；舊 v008 封存 inventory 繼續驗證 |

固定候選 release 為 `rag-v2-v004-f3339ceae77c`，candidate SHA-256 為
`f3339ceae77c380f42b3c2823b28216827ef48d057129a9c5f5edd40c9e808dd`。
新 runtime policy SHA-256 為
`a7d8dd163e54bb5cb11f1ea4004e3a6b75b9faff98290067e745125cc6ac5758`。
這些值識別本機候選，不代表外部同步或啟用授權。

本機回歸結果（不是 live 驗收）：

- Core 指定 unit：preview、candidate、projection importer、embedding importer，56 passed（11.18s）。
- Agent Runtime 全套：533 passed（15.32s）。
- RAG v008 / v009 audit 指定整合測試：4 passed（5.12s）。
- 本次修改的 Agent runtime / retriever / 新測試 Ruff lint 通過；`git diff --check` 無空白錯誤。

以上結果來自本機命令輸出；尚未建立涵蓋整個新階段的最終交付 regression evidence package，
也未執行全專案 suite 或遠端 CI。後續程式變更需重跑相關驗證並更新治理 successor，不能沿用舊結果。

剩餘步驟：

1. 已補上純函式 [向量重用前置驗證](../../services/core-api/app/rag_embedding_reuse_preflight.py)：
   比對完整 snapshot projection 欄位、原始 embedding artifact 綁定、完整 ID 對照及 float32 向量指紋。
   caller 必須先使用既有 hash-pinned loaders，並從同一個明確唯讀交易取得 snapshot。
   新增 32 個測試（包含 726 筆候選＋合成向量），與前述 Core 指定回歸合跑為 88 passed（10.10s）；
   新增兩個檔案 Ruff lint / format 通過。這不是遠端驗證證據，也不涵蓋在 snapshot 後發生的撤銷。
   本函式未納入已封存的 v009 稽核，後續同步交付需新增稽核證據，不得宣稱舊稽核涵蓋它。
   尚需建立取得／鎖定 live rows 的同步 adapter；未驗證遠端全量向量，未建立 DB apply 工具或新 writer principal。
2. 取得目前 Supabase 開發資料庫建立新 staging release，以及本機 Agent 切換的明確授權。
3. 在單一交易內同步新版本、讀回核對與產生 truthful receipts；保留舊 release，不重建付費 embeddings。
   若向量驗證失敗則停止，不自動產生新 embeddings。
4. 受控 live smoke 通過後切換本機 Agent，完成「長照法」「長照法第二條」的引用與安全負例、Browser E2E 驗收。

本節為同步前紀錄；最新實機進度見下一節。Production 仍未核准。

## 8. 已核准同步與實際問答（2026-09-10）

[本次授權](rag-law-sync-authorization-20260910.json)獨立於歷史 acceptance；不覆寫舊核准文件。
[實際執行結果](rag-law-sync-live-result-20260910.json)記錄新 release、交易 receipts、獨立讀回與問答結果。

- 新版本 726 筆 projection 與 726 筆既有向量已在同一交易匯入；獨立唯讀連線再驗全量 metadata、向量與 profile 通過。
- 只有 71 筆法規治理欄位變更。其餘 655 筆限制、包括 `_0048` 的高風險／stop 封鎖保持不變；舊 release 完整保留。
- 原始 temporary embedding 檔已遺失，因此本次證據明確標示「現存 DB 的新匯出」；不能宣稱與遺失原檔逐位元相符。
  新舊 export 的 hash 與實際 readback 相符，沒有重新呼叫 document embedding provider。
- 本機 `.env` 三個非秘密 RAG release / policy 設定已切換。發現並修正本次本機啟動器的 dotenv interpolation 問題，
  Agent 以 `.qa/run_law_agent.py` 啟動後，真實 BFF → Core → Agent 問答兩題皆為 `SUCCESS / ALLOW`。
- 「長照法第二條」回覆符合候選第二條的主管機關內容，附官方引用與 deterministic assessment advisory。
  Elder / Family / Care Professional 的直接 retrieval 都取得包含第二條的 5 筆合格結果；不允許用途仍為 `NO_DATA`。
- 同步沿用現有開發 DB 連線，沒有變更 grants 或新增 least-privilege principal。此項仍是 production 前待辦，不宣稱已完成。
- 最初驗證只有 HTTP BFF 完整鏈路；後續已使用 Playwright 真實瀏覽器登入既有 synthetic Elder
  帳號，透過打字模式送出兩題，皆為 HTTP 200、`SUCCESS / ALLOW`。畫面回答、可展開的官方來源
  連結與 assessment advisory 均已核對，測試後登出。沒有修改法規時效或 Production gate。
  [瀏覽器驗收紀錄](../../.qa/rag-law-browser-verification-20260910.json)與對應截圖保留實際 viewport
  量測：1440／390／430px 設定下無水平溢出；375px 設定下有約 3 CSS px 水平溢出，文字與引用
  仍可閱讀，尚未修正。這是本機既有 production build 的文字問答驗收，不是真機語音測試。

回復設定：僅在確認舊 release 的最新撤銷狀態仍安全後，切回第 2 節舊 release 與 v003 policy／原 SHA，
再以支援 dotenv interpolation 的方式重啟 Agent。舊資料不得因回復而解除後續封鎖。

### 最終本機回歸證據

輸入在 collection 前凍結，collection / execution 後再次比對；測試數由 JUnit XML 解析，
執行命令、node digest、stdout log hash 見
[提交前最終回歸紀錄](../../.qa/law-regression-g4gbow3x/report.json)。
較早的[首次完整通過紀錄](../../.qa/law-regression-8ln63geo/report.json)保留為歷史證據。

- Core 修復相關 unit：99 passed、0 failed / error / skipped。
- Agent Runtime 全套：533 passed、0 failed / error / skipped。
- RAG Ingestion 全套：328 passed、0 failed / error / skipped。
- 提交前的最終執行時間為 Core 71.250s、Agent 24.766s、RAG 403.015s，三者皆使用相同凍結輸入。
  Git 暫存区的 126 個 v010 稽核輸入亦已逐檔對照原始 SHA-256，沒有不符。
  LF 規則使用子目錄 `.gitattributes`，根目錄及歷史 acceptance 雜湊不變。
- 本次新增／修改程式的指定 Ruff lint 與格式檢查通過。
- v010 稽核綁定同步工具、測試與獨立授權，inventory SHA 為
  `1552d6cea12664eab76dc1aff0fda5f3be4381ce359dbcc93b0f5b5f7c59548f`。
  最初未通過 lint 的本機 v010 候選已撤回並保留於 `.qa/law-sync-audit-v010-failed-lint-20260910/`；
  正式位置是 lint 修正後重建並通過全套測試的版本，歷史 v001–v009 未覆寫。

本機未執行 Core DB integration（沒有 disposable TEST_DATABASE_URL）或重新 Frontend build。
本機前端沿用既有 build，未修改 UI；實際 Browser 文字問答已另行驗證，離線 regression report 中
原有的 browser 欄位保留當時歷史狀態，不覆寫成後續結果。遠端 PR CI 以該 PR 實際執行結果為準。

PR #40 的首次 `changes` 檢查發現 Core RAG 匯入器／法規測試已成為 v009／v010 稽核輸入，
但舊 impact policy 未選取 `rag-quality`。已新增精確 Core RAG 路徑前綴並升至 policy version 2，
維持其他 Core 路徑原有選擇；CI instrumentation／impact 本機 26 項測試與 lint／format 通過。
未修改 workflow YAML 或放寬 aggregate gate；後續遠端執行仍需以 GitHub 結果判定。
