# 公開知識 RAG：現況、有效規則與 release 沿革

整理日期：2026-10-15（自根目錄 AGENTS.md／CLAUDE.md 拆出）。Agent 端實作規則另見
[`services/agent-runtime/AGENTS.md`](../../services/agent-runtime/AGENTS.md)。查現況以當次唯讀回讀輸出為準，
不要沿用本檔快照。

## 現況（2026-10-07 起）

- 本機 development 使用 `knowledge-v009-5046fa3d59c4`（713 筆資料與向量，603 重用、110 新向量且確認未截斷），
  `RAG_EVIDENCE_V3_ENABLED=true`、`KNOWLEDGE_ROUTER_V2_ENABLED=true`（本機 `.env`；repository 預設關閉）。
  v008／v004 保留，已實測 v009→v008→v009 回退。見 [v009 rollout](rag-v009-rollout-20261006.md)。
- 公開問答期限分層：Gemini grounded 40 s、V3 全程 45 s、Core public 50 s、問答 BFF 60 s；一般 ungrounded／companion／其他 BFF
  timeout 不變。生成預算見 agent-runtime AGENTS（[10-13 驗收](live-acceptance-20261013.md)）。
- 入口：長者文字陪伴、家屬 `/family/knowledge`（固定 family_caregiver）、照服員 `/staff/knowledge`（限 ACTIVE
  DAYCARE／HOME_CARE_WORKER，固定 care_professional），均無個案查詢或寫入。
- 全庫 `review_status=needs_review`、`production_approved=false`、`retrieval_activation_status=NOT_AUTHORIZED`；production 未啟用，human review 未完成，真人語音未驗收。

## 仍有效的規則

- **外部寫入需逐次授權**：匯入、activation 或改 release 前須使用者明確授權該範圍（例如 2026-09-10 的授權只涵蓋該次
  71 筆法規）。不可直接改 immutable release rows 卻沿用原 record／candidate hashes；先產生差異、設計 successor
  與安全回復。
- 不得把 pending、needs_review、AI 判定或 synthetic 結果冒充人工 verified；unsigned development override 不是
  production approval。
- `NO_DATA` 先核對 live projection 的 `retrieval_eligible`／block reasons，再看 policy 與 ranking；本機補 metadata
  不會解除遠端封鎖。
- SUCCESS／PARTIAL／NO_DATA 是狀態，不是語意準確率；各輪與單題複測不可拼成新整批分數；引用 ID 與原文錨點通過
  不等於語意正確，Gemini JSON schema 只約束形狀。
- 檢索、排序、span 引用、PDF 排版、read-only 交易、生成預算與失敗診斷等程式規則見
  [`services/agent-runtime/AGENTS.md`](../../services/agent-runtime/AGENTS.md)「RAG 與生成的實作規則」。
- Ingestion allowlist（`services/rag-ingestion`）：未簽署時只有 staging 明確 `RAG_REQUIRE_OWNER_SIGNATURE=false` 才允許 unsigned
  development override，且不得關閉 `RAG_ALLOWLIST_EXPECTED_SHA256` 比對或略過來源、Chunk、數量、完整 Allowlist 驗證；receipt／log
  標示 `governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、`production_approved=false`。Production 須正式簽署並設
  `RAG_PRODUCTION_ENABLED=true`。
- V2 policy 模式：`RAG_SOURCE_FAMILY_POLICY_PATH` 與 `..._EXPECTED_SHA256` 缺一或不符、或仍開
  `RAG_STAGING_ALLOW_ALL_AUDIENCES` 就 fail closed；runtime image 不內建 `data/rag*`；production 不得用
  `RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true`。V1／V2 契約仍為 3–5 筆引用。
- 2026-10-02 起不再要求每次程式改動新增 manifest、snapshot、byte audit successor（不建 v021）；逐筆人工覆核、
  E3 工作台與 qrels 填寫退出日常必經路徑。保留真實來源、來源／資料版本與內容 hash；v020 以前 audit 只是歷史。
- 個人診斷、長照資格、等級與補助額度不得由 AI 判定；高風險法條仍拒絕。

## 沿革（摘要）

| 日期 | 事件 | 文件 |
| --- | --- | --- |
| 2026-08-25 | 套用 `rag_public` migration；匯入 `rag-v2-v002-bab68588963b`（17 sources／726 chunks）與 726 個 Google embeddings；PostgreSQL Hybrid SearchBackend smoke | [runtime policy 整合](rag-v3-runtime-policy-integration.md) |
| 2026-08-26 | 本機 immutable 候選 `data/rag-v3/candidates/v003/`（726 筆 verified）；source-family policy v002 | 同上 |
| 2026-08-27 | runtime policy v002／v003（554 筆 ordinary 候選、32 筆 purpose overlay）；長者「長照法」live smoke | 同上 |
| 2026-09-10 | 依獨立授權同步 `rag-v2-v004-f3339ceae77c`（只改 71 筆長照法治理欄位，舊 release 保留）；runtime policy v004 | [治理同步計畫](rag-law-governance-sync-plan-20260909.md)、`rag-law-sync-live-result-20260910.json` |
| 2026-09-29 | `scripts/rag/sync_law_repair.py verify` 唯讀複驗 v004 與 09-10 紀錄一致 | `rag-law-sync-verification-20260929.json` |
| 2026-10-02 | RAG 簡化 1–4 批：退役 audit 流程、本機 658 chunks 管線、V3 Hybrid＋生成、真實基準 7／5／4 | [1](rag-simplification-phase1-20261002.md)、[2](rag-simplification-phase2-20261002.md)、[3](rag-simplification-phase3-20261002.md)、[4](rag-simplification-phase4-20261002.md) |
| 2026-10-02 | 授權後匯入 `knowledge-v008-aae34e5095e6`（658 筆） | 第 4 批末節 |
| 2026-10-05 | development 切 v008＋V3＋router v2；固定 16 題 11／5／0；家屬與專業公開問答入口（#69、#70） | [檢索與引用](rag-retrieval-and-quotes-20261005.md)、[家屬](family-public-knowledge-20261005.md)、[專業](staff-public-knowledge-20261005.md) |
| 2026-10-06 | 生成模型升 `gemini-3.8-flash`；55 筆 PDF 版面來源修整 | [模型](gemini38-upgrade-20261006.md)、[版面](rag-pdf-layout-repair-20261006.md) |
| 2026-10-07 | development 啟用 v009；訓練時數題診斷修正（#74） | [v009](rag-v009-rollout-20261006.md)、[診斷](rag-training-diagnostics-20261007.md) |
| 2026-10-13 | 真實公開問答驗收，CA07 截斷修正 | [驗收](live-acceptance-20261013.md) |

注意：`data/rag-v3/candidates/v003/` **不是** v004 的後繼，而是同樣分支自 v002 的平行候選；直接同步會新開放 224 筆並
關閉 71 筆長照法。這是 v004 時期的歷史約束，現行 development 已改用 `knowledge-v009`。
