# RAG v3 source-family runtime policy integration

- 狀態：本機／staging runtime candidate
- Runtime policy：`v003`
- 上游 source-family policy：`v002`
- Citation candidate：`v003`
- Production：封鎖

## 已實作的資料流

`/api/v2/rag/retrievals` 先在固定的 554 筆官方、公開、ordinary-RAG 候選內執行 hybrid search，
最多取得 50 筆候選；Retriever 再逐筆驗證 v002 chunk ID、source ID、v003 文字 SHA-256、角色、
purpose 與 assessment metadata，最後只回傳 3–5 筆 v003 citation。搜尋排序不負責安全判斷。

啟用 hash-pinned runtime policy 時，PostgreSQL 先以固定 554 個 prior chunk IDs 取代遠端舊版
governance metadata；Retriever 隨後仍逐筆驗證 source ID、v003 文字 SHA-256、角色與 purpose。這讓
本機已核准的 immutable policy 能覆蓋尚未同步的遠端 v002 metadata，又不會讓清單外或文字被改動的
資料進入回答。未啟用 runtime policy 的 legacy 路徑仍必須通過遠端 public／official governance。

四個角色 `elder`、`family_caregiver`、`care_professional`、`system_admin` 都可搜尋同一個固定
候選池。`requires_official_assessment=true` 或 `requires_professional_assessment=true` 不再因角色
阻擋一般資訊；Runtime 會在模型回覆後、引用來源前固定加入主管機關／專業人員諮詢提醒。模型不得
替個人判定診斷、長照資格、等級、補助額度或個別照護需求。assessment 欄位缺失／非 boolean，或
chunk 沒有 `allowed_purposes` 時仍一律拒絕回覆。

v002 依 Owner 明確決定，把 ordinary runtime candidates 的 220 筆 professional assessment `null`
與 5 筆 official assessment `null` 映射為 `true`，不改寫 v003 Chunk bytes。554 筆中有 522 筆可通過
response metadata gate；其中 372 筆命中時需附 deterministic advisory。

v003 再以 staging-only purpose overlay 分類原本空白的 32 筆 A 單位手冊 chunks，使用既有 enum 並讓
來源層與 chunk 層都包含 `general_information`，因此目前 Core 的自然語言知識提問可通過 purpose gate。
這 32 筆分類仍標記 `needs_review`，不代表人工確認或 Production 核准；v003 Chunk bytes 未修改。
完成後 554 筆均具備 response metadata。5 筆「一般風險值」仍由 policy overlay 映射為 `low`；high／unknown、
`stop_normal_rag=true`、非 current 與 3 個 research sources 不在普通搜尋候選內。

## 啟用方式

本機 repository 執行時設定：

```dotenv
RAG_MODE=staging
RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true
RAG_STAGING_ALLOW_ALL_AUDIENCES=false
RAG_SOURCE_FAMILY_POLICY_PATH=data/rag-v3/governance/source-family-policy/runtime/candidates/v003/source-family-runtime-policy.json
RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256=99aa1dd6ccf90970c798664fedaff9ae3dd2f769437ebebc4a54c07478a1b5bd
```

path／SHA-256 缺一、digest 不符、policy contract 不符，或仍開啟 legacy all-audience override 時，
Agent Runtime 不建立 Retriever，並 fail closed。Runtime image 不內建任何 `data/rag*` 內容；若要在
container staging 測試，部署者必須把已驗證的 v003 policy 以唯讀 config mount 注入，再設定相同的
獨立 SHA-256 pin。

## Golden Query 邊界

`config/rag/source-family-golden-queries-v003.json` 固定 10 個離線 policy／citation case：一般資訊無
advisory、四角色的 assessment=true 資料成功並附 advisory、長者查詢長照法成功並附 advisory、
null→true 表單資料成功、A 單位一般資訊成功，以及不相符 purpose 仍拒絕；另驗證 high-risk chunk 與
research source 不在搜尋 projection。

這些測試只驗 deterministic policy 與 citation gate，不宣稱已驗證真實 query embedding、遠端資料庫
排序、回答品質或 recall。live relevance Golden Query 仍標記 `NOT_EXECUTED`。

2026-08-27 另完成一筆實際長者帳號 smoke：問題「長照法是什麼？」會先將常用縮寫展開成正式法規
名稱，legal PostgreSQL search 允許 raw lexical exact-title match 獨立通過 0.7 relevance gate，最後
從 `moj_long_term_care_services_act_20210609` 取回 5 筆受治理 chunks；完整回覆為 `SUCCESS/ALLOW`，
含 2 個去重後公開引用與 deterministic assessment advisory。這一筆 smoke 不等於完整 live Golden
Query suite。

## 長者帳號測試

既有 `scripts/seed_demo.py` 可在本機 synthetic development 資料庫建立
`elder.demo@kinsun.local`、`family.demo@kinsun.local`、`staff.demo@kinsun.local`。它要求明確的
`DEMO_ACCOUNT_PASSWORD`、原生登入已開啟，且只允許空的／符合 development opt-in 的資料庫。
本次 runtime policy integration 不重設資料庫，也不對 Supabase 或 Production 建立帳號。

## 尚未解除的封鎖

- 尚未將 v003 與 runtime policy 同步至 Supabase 或其他外部 search backend。
- 尚未使用長者登入介面跑完整真實端到端 Golden Query；離線 policy cases 已通過。
- A 單位 32 筆 purpose 是 AI-assisted staging classification，仍需 Owner 逐筆確認後再建立 verified successor。
- 尚未建立獨立 read-only database principal、activation／rollback 與 Production approval。
- Production 不得使用 `RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true`，也不得由此 candidate 自動升級。
