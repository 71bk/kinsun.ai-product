# RAG v3 source-family runtime policy integration

- 狀態：本機／staging runtime candidate
- Runtime policy：`v001`
- 上游 source-family policy：`v002`
- Citation candidate：`v003`
- Production：封鎖

## 已實作的資料流

`/api/v2/rag/retrievals` 先在固定的 554 筆官方、公開、ordinary-RAG 候選內執行 hybrid search，
最多取得 50 筆候選；Retriever 再逐筆驗證 v002 chunk ID、source ID、v003 文字 SHA-256、角色、
purpose 與 assessment metadata，最後只回傳 3–5 筆 v003 citation。搜尋排序不負責安全判斷。

四個角色 `elder`、`family_caregiver`、`care_professional`、`system_admin` 都可搜尋同一個固定
候選池。長者與家屬若命中需要官方或專業評估的內容，該筆不可直接回覆；照護專業與系統管理角色
仍須通過 purpose 與完整 assessment metadata。欄位為 `null` 或 chunk 沒有 `allowed_purposes` 時
一律拒絕回覆。

554 筆中有 302 筆具完整 response metadata。其餘 252 筆仍可參與搜尋，但若未通過上述回覆 gate
不會進入答案。5 筆「一般風險值」由 policy overlay 映射為 `low`；high／unknown、
`stop_normal_rag=true`、非 current 與 3 個 research sources 不在普通搜尋候選內。

## 啟用方式

本機 repository 執行時設定：

```dotenv
RAG_MODE=staging
RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true
RAG_STAGING_ALLOW_ALL_AUDIENCES=false
RAG_SOURCE_FAMILY_POLICY_PATH=data/rag-v3/governance/source-family-policy/runtime/candidates/v001/source-family-runtime-policy.json
RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256=<由 immutable package 驗證結果取得>
```

path／SHA-256 缺一、digest 不符、policy contract 不符，或仍開啟 legacy all-audience override 時，
Agent Runtime 不建立 Retriever，並 fail closed。Runtime image 不內建任何 `data/rag*` 內容；若要在
container staging 測試，部署者必須把已驗證的 policy 以唯讀 config mount 注入，例如掛在
`config/rag/source-family-runtime-policy-v001.json`，再設定相同的獨立 SHA-256 pin。

## Golden Query 邊界

`config/rag/source-family-golden-queries-v001.json` 固定 10 個離線 policy／citation case：四角色的一般
資訊成功、長者／家屬的專業評估內容拒絕、專業／管理角色的受控成功、purpose mismatch 拒絕、
assessment metadata 不完整拒絕；另驗證 high-risk chunk 與 research source 不在搜尋 projection。

這些測試只驗 deterministic policy 與 citation gate，不宣稱已驗證真實 query embedding、遠端資料庫
排序、回答品質或 recall。live relevance Golden Query 仍標記 `NOT_EXECUTED`。

## 長者帳號測試

既有 `scripts/seed_demo.py` 可在本機 synthetic development 資料庫建立
`elder.demo@kinsun.local`、`family.demo@kinsun.local`、`staff.demo@kinsun.local`。它要求明確的
`DEMO_ACCOUNT_PASSWORD`、原生登入已開啟，且只允許空的／符合 development opt-in 的資料庫。
本次 runtime policy integration 不重設資料庫，也不對 Supabase 或 Production 建立帳號。

## 尚未解除的封鎖

- 尚未將 v003 與 runtime policy 同步至 Supabase 或其他外部 search backend。
- 尚未使用長者登入介面跑真實端到端 Golden Query。
- 尚未建立獨立 read-only database principal、activation／rollback 與 Production approval。
- Production 不得使用 `RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true`，也不得由此 candidate 自動升級。
