# RAG 簡化第 2 批：本機知識資料管線

依使用者 2026-10-02 授權，取消逐筆人工覆核與反覆封存前提，建立可直接重跑的本機整理流程。三位 GPT-6.1 Sol subagents 分別負責 corpus 檢查／回歸測試、embedding 計畫／CLI、Core loader；主代理負責資料契約、compiler、整合與最終覆核。

## 這批完成什麼

- 新 `knowledge-chunk-v1` 契約只統整 source、content、policy、provenance；來源、定位、版本、文字與 embedding hash 均保留。
- 新 `prepare_knowledge.py` 預設 dry-run。新 compiler 與 Core loader 不匯入舊人工工作簿、allowlist、acceptance 或 audit 模組。
- 自動拒絕重複 ID、錯誤 hash／字數、缺少定位、非官方網址、錯誤 metadata 型別、相互矛盾的現行來源版本、Restricted 資料及空輸出；排除項目仍保留在原始 corpus。
- embedding 計畫採精確 UTF-8 內容＋完整 profile 比對；profile ID 相同但模型／設定不同也會拒絕錯誤 cache。
- Core loader 重新驗證 schema、內容 hash、來源及數量，建立 `ProjectionBatch`；不信任 report 自報的筆數，不寫資料庫。

不建立 audit v021、封存 ZIP 或人工填寫欄位。新輸出是可重跑的資料集，不是新的封存鏈。舊相容工具與歷史資料仍保留，不再作為新入口的必經相依。

## 735 筆候選的處理結果

| 分類 | 筆數 | 處理 |
| --- | ---: | --- |
| 官方知識 | 658 | 納入本機知識候選，涵蓋 14 個來源 |
| 非官方研究／量表 | 75 | 不納入本次官方知識搜尋集合；原文保留供後續研究用途 |
| 已被取代的流程 | 1 | 排除舊流程，保留獨立的新流程來源 |
| 只有導覽用途的文字 | 1 | 排除自我檢測導覽標籤 |

原始 735 筆、17 個來源沒有空白正文、重複 ID、完全相同正文或 hash 不符。不是所有短 chunk 都無用：短條文與 BA 說明仍有完整意義，不依字數直接刪除。這批沒有重新改寫正文或拆分長表格；既有兩個 pilot 的重切候選已包含在 735 筆輸入中。

658 筆保留資料仍有下列品質提示：

| 提示 | 筆數 | 意義 |
| --- | ---: | --- |
| 現行性 unknown | 295 | 尚未以新官方來源確認仍現行，不改成 current |
| assessment metadata 有 null | 137 | 不擅自改成「無需專業／官方評估」 |
| audience／purpose 缺漏 | 65 | 保留空值，留待第 3 批統一准入規則 |
| 來源版本 unknown | 8 | 不由程式猜測日期 |
| 正文超過 1,800 字 | 46 | 包含長表格；後續以檢索失敗個案決定是否再拆 |
| 正文少於 100 字 | 43 | 短條文可能完整，只提示、不自動刪除 |
| 舊 retrieval 限制 | 512 | 舊 policy 尚未調整，保留原值 |

合計 1,106 個提示會重疊，**不是 1,106 個人工任務**。來源檢查目前限於本機內容、URL 與定位一致性，沒有上網重新確認法規、服務流程或發布日期，也不能由 hash 證明語意正確。缺少實體 `source_file` 的記錄仍可由官方 URL／locator 定位，不虛構原始 PDF hash。

## 使用方式

於 repository root 執行：

```powershell
uv run --project services/rag-ingestion python scripts/rag/prepare_knowledge.py
uv run --project services/rag-ingestion python scripts/rag/prepare_knowledge.py --write --output .rag-work/knowledge-v007
```

預設輸入 `data/rag-rechunk/successor/v001/corpus.jsonl`，比較基線 `data/rag-v2/candidates/v004/chunks`，dataset version `v007`。可用 `--corpus`、`--baseline`、`--dataset-version`、`--profile-registry`／`--profile` 指定輸入。`.rag-work/` 已列入 Git ignore。

`--baseline` 同時接受舊 RagChunkV2 JSONL 與前一次新流程輸出的 `chunks.jsonl`（也可指定其所在目錄）。新格式省略冗餘字數欄位，仍重新檢查 schema 與兩種內容 hash，讓後續更新能直接比較前一批資料。

只產生三份檔案：

- `chunks.jsonl`：658 筆正規化的官方知識候選。
- `report.json`：統計、自動檢查、排除原因與可追蹤 chunk ID。
- `embedding-plan.json`：每筆 REUSE／EMBED、內容 hash、profile 與重複工作去重關係；不含向量。

相同命令再次執行會接受內容完全相同的輸出；內容不同時拒絕覆寫，需指定另一個工作目錄。原始版本永遠不在此步修改。Core 可用 `app.rag_knowledge_importer.load_knowledge_batch(Path(...))` 讀取這個目錄；這個函式只建立 batch，沒有呼叫 importer 寫入 DB。

## Embedding 重用的真實邊界

相對 v004，**631 筆 embedding 文字完全相同，27 筆不同**。這只是文字比較，不等於取得或驗證了 631 個向量。

目前 registry 對應 Google `gemini-embedding-001`／1024 維／`RETRIEVAL_DOCUMENT`／config `1.0.0`。`model_version` 記錄配置中的模型識別，不宣稱已查到 provider 不變的底層 revision。改動模型、維度、task、標題、截斷、正規化等設定，必須更新 profile／config 身分，不能只沿用舊 ID。

若提供 `--cache local-cache.json`，其格式為 `schema_version: knowledge-embedding-cache-v1`，另含：

- `profiles`：保存當時完整 `profile_id`、`provider`、`model_id`、`model_version`、`document_task_type`、`dimension`、`config_version`，必須逐欄符合可信 registry。
- `entries`：每筆 `profile_id`、`embedding_text`、`embedding_text_sha256` 與可選的 `vector`。

只有文字／hash／profile 完全符合且實際供應非零、有限數值、維度正確的 vector 才計為 `available_reuse`。只有 metadata 則計為 `potential_reuse`，仍需 EMBED；重複文字可去重 provider 工作，但不冒稱向量已存在。cache 拒絕不明 profile；所有新入口的 JSON 讀取都拒絕重複 keys 及非有限數值。

本次未取得外部向量 cache，故實際計畫為 **0 筆 available reuse、658 筆待 embedding**，並未執行或付費呼叫 embedding。後續可在獲授權的環境讀取既有向量，再由同一 planner 檢查是否真的能重用 631 筆；不可直接憑舊筆數宣稱已重用。

## 與後續 Hybrid RAG 的界線

658 是保留的官方知識候選數，**不是現在可供使用者查詢的筆數**。原 `retrieval_eligible` 仍只有 146 筆為 true；needs_review、unknown、風險、scope 與 assessment 原值皆保留。移除工作簿前提不會把它們改成 verified 或自動准入。

本批沒有修改 runtime／SQL、啟用 V3、執行 DB import、provider 切換或 release activation。現有 development release 仍為 `rag-v2-v004-f3339ceae77c`，policy v004。既有的最低 3 筆規則亦尚未變動。

下一批一起調整 runtime／SQL：以自然問句執行 dense＋關鍵字 Hybrid 檢索，從足夠的實際證據生成回答，移除精確題目、人工 support sets、固定答案與最低 3 筆門檻；資料不足時明示缺口。第 4 批再以真實問題驗證檢索、引用及答覆品質，針對長表格等失敗個案調整切割。上網搜尋若加入，是查新／補缺的獨立來源，不取代官方知識與使用者資料權限。

## 驗證

- RAG ingestion 全套：534 passed（235.50 秒）。最終覆核再補「正規化輸出可作下一次 baseline」及兩個篡改負例後，compiler／CLI 定向測試 41 passed（11.12 秒）。共 537 個不同案例有通過結果；不是宣稱另跑一次完整 537-case suite。
- Core 新／舊 projection loader、embedding importer 與 reuse preflight：71 passed（8.26 秒）。
- CI workflow／影響規則／telemetry：28 tests passed；CI 的 RAG lint／format 已納入新 CLI。
- `scripts/validate_contracts.py contracts` 全數通過；Ruff lint／format 通過，涵蓋 ingestion、CLI、CI 及新 Core loader／tests。`git diff --check` 通過。
- 真實 735 筆輸入完成 WRITE：658 retained、77 excluded、0 errors；相同命令再次執行成功，輸出內容一致。
- Core 唯讀載入本機輸出：658 chunks、14 sources，batch `knowledge-v007-55870f086ea2`；363 current／295 unknown、needs_review 與非 production 狀態保留。
- 新輸出 JSONL 作為 baseline 的實際 dry-run 通過，正確得到 658 unchanged／0 changed；依然是 0 available vectors，不把基線當向量 cache。
- registry 的 profile ID 已用既有 Core `EmbeddingProfileBinding` 在本機重新計算核對一致。模型／config 同 ID 變更、缺少 cache snapshot、錯誤 hash、重複 JSON keys、浮點 overflow、Restricted 資料與空輸出均有拒絕測試。

以上是本機工程及內容完整性驗證，不是回答品質評分、線上來源新鮮度驗證或 production 核准。本次沒有外部 DB／embedding 呼叫；未執行 runtime／SQL 整合或使用者實際問句評測。
