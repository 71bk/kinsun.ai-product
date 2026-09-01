# 長期照顧服務法 RAG 雲端、本地與 Supabase 比對紀錄

- 盤點日期：2026-09-01（Asia/Taipei）
- 盤點方式：Google Drive、repository 與 Supabase 唯讀檢查
- 官方來源：[全國法規資料庫－長期照顧服務法](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070040)
- 官方版本日期：2021-06-09
- Production 狀態：`BLOCKED`

## 1. 結論

長期照顧服務法的條文原文並未缺失。Google Drive、本地 RAG candidate 與 Supabase 都有 72 個條文級資料單位；目前無法穩定回答「長照法有幾條」的主因是：

1. 尚未建立 `law_article_count` 或等價的文件層級 Structured Record。
2. Supabase 基礎 projection 中，長照法可檢索數量為 0。
3. 普通向量檢索只會取回少量條文 chunk，不能可靠地計算整份法律的條文總數。

精確回答應同時保留兩種數字語意：

- 最高條號：第 66 條。
- 增訂條文：第 8 條之 1、第 32 條之 1、第 32 條之 2、第 39 條之 1、第 47 條之 1、第 48 條之 1，共 6 條。
- 實際有效條文項目數：72。

## 2. Google Drive v005 盤點

### 2.1 來源位置

- RAG 根資料夾：[Google Drive RAG 資料夾](https://drive.google.com/drive/folders/1J0iow5nnpsza0MOkmvQy7SlF2KiaEMMO)
- 長照法 v005：[處理批次 v005](https://drive.google.com/drive/folders/1fcR0gceR13eOf6o6xW8NizIV80I0OpTG)
- Chunk JSONL：[長期照顧服務法_Chunks_v005.jsonl](https://drive.google.com/file/d/1VW0RLDiAHsPacPKpuZ9GoAR4lqBVlIJH/view)
- 驗證報告：[長期照顧服務法_Validation_Report_v005.md](https://drive.google.com/file/d/1WP0RplCuNfSLJkFih_zEj5bymN_GqhBG/view)
- 人工審查清單：[長期照顧服務法_Manual_Review_Checklist_v005.md](https://drive.google.com/file/d/1OgHERo7GjLa2rMoMBD42ePvSgWbTb_kN/view)
- 管理表：[AWS 長照 RAG 資料管理表](https://docs.google.com/spreadsheets/d/18tmD_10bOSJ099GvcM6-vEk3L-oZZRSMUTGzjkNqT3E/edit)

### 2.2 v005 JSONL 結果

| 項目 | 結果 |
| --- | --- |
| 檔案大小 | 407,328 bytes |
| SHA-256 | `64a0a6fd670e3c33e34459c79c274af6d07eda18dd5e8e4dfcfd3c2a1bc6a34b` |
| JSONL 筆數 | 72 |
| `chunk_index` | 1–72 |
| 第一筆 | `moj_long_term_care_services_act_20210609_article_001` |
| 最後一筆 | `moj_long_term_care_services_act_20210609_article_066` |
| `review_status` | 72 筆 `needs_review` |
| `embedding_status` | 72 筆 `not_started` |
| `requires_professional_assessment` | 72 筆為 `null`／未設定 |
| `requires_official_assessment` | 70 筆 `false`、2 筆 `true` |
| `retrieval_eligible` | v005 JSONL 未提供此欄位 |
| Production Gate | `BLOCKED` |

v005 驗證報告記載：JSON 解析、索引連續性、ID 唯一性、文字 hash、官方條文逐條自動比對及 `embedding_text = text` 均通過；但獨立 Human Source Review、Embedding 與 OpenSearch indexing 均未完成。自動比對通過不等同人工審查完成。

### 2.3 Google Sheets 管理表結果

管理表的「結構化資料」工作表中，長照法只有 1 筆 Structured Record：

- `record_id`：`moj_long_term_care_services_act_20210609_workflow_article_008_02`
- `record_type`：`workflow_rule`
- 用途：記錄第 8 條第 2 項之申請與評估流程。

目前沒有 `law_article_count`、`highest_article_number`、`inserted_article_count` 或 `effective_article_count` 等精確計數紀錄。

管理表的「Chunk檔案總表」只登記 v001、v002、v003，並將 v003 標為 current；雲端已有的 v004、v005 尚未同步進該管理表。因此，Google Drive 目前存在「檔案版本已到 v005，但管理表只到 v003」的版本登記落差。

## 3. 本地 RAG v003 candidate

本地檔案：

`data/rag-v3/candidates/v003/chunks/moj_long_term_care_services_act_20210609.rag-chunk-v3.v003.jsonl`

| 項目 | 結果 |
| --- | --- |
| 檔案大小 | 368,858 bytes |
| SHA-256 | `2abf9eedd4b4567b4537e8bc2c6a880d35cf45ab5535f9a1c5a0d1e623a58671` |
| Chunk 數 | 72 |
| `chunk_index` | 1–72 |
| `review_status` | 72 筆 `verified` |
| `embedding_status` | 72 筆 `reuse_verified` |
| `production_approved` | 72 筆 `false` |
| `retrieval_eligible` | 72 筆 `false` |
| `requires_professional_assessment` | 72 筆 `null` |
| `requires_official_assessment` | 70 筆 `false`、2 筆 `true` |

本地 v003 的 provenance 指向雲端 `長期照顧服務法_Chunks_v005.jsonl`，並保留 v005 的條文文字與 `text_sha256`。本地 v003 是治理後的 successor candidate，不應再將雲端 v005 直接視為 runtime authority。

本地 v003 已記錄 owner review evidence 並重用既有 embedding，但仍維持 `production_approved=false`。其基礎 `retrieval_eligible=false` 是由 `requires_professional_assessment=null` 造成；staging runtime 應透過 hash-pinned source-family policy overlay 決定可用候選，而不是批次硬改所有 chunk。

## 4. Supabase 現況

目前 runtime 指向：

- Search backend：PostgreSQL。
- Release：`rag-v2-v002-bab68588963b`。
- Release 總 chunk：726。
- 長照法 chunk：72。
- 長照法 embedding：72。
- 長照法基礎 projection 可檢索數：0。

長照法 72 筆 Supabase projection 的 `requires_professional_assessment` 均為 `null`，因此在未啟用 policy overlay 的基礎查詢路徑中會被 fail-closed filter 排除。

目前 repository 已有 staging runtime policy：

```text
data/rag-v3/governance/source-family-policy/runtime/candidates/v003/source-family-runtime-policy.json
```

Policy SHA-256：

```text
99aa1dd6ccf90970c798664fedaff9ae3dd2f769437ebebc4a54c07478a1b5bd
```

該 policy 提供 554 個 staging candidate，長照法一般條文中有 71 個可進 ordinary retrieval candidate pool；涉及高風險權益／通報處理的第 44 條維持特殊安全路由。Policy overlay 只能用於 staging 驗證，不能視為 Production 核准。

## 5. 版本角色

```text
Google Drive v005
  來源與交付產物；72 筆條文；needs_review；未執行 embedding
        ↓ 保留原文與 hash lineage
本地 RAG v003 candidate
  治理後 successor；72 筆 verified；embedding reuse_verified
        ↓ hash-pinned runtime policy overlay
Supabase v002 release
  目前實際 data plane；72 筆 embedding；基礎 projection eligible=0
```

因此：

- 雲端 v005 是來源／交付基底。
- 本地 v003 是目前應採用的治理候選。
- Supabase v002 是現行實際搜尋資料層。
- v003 policy overlay 是 staging runtime 的過渡整合方式。

## 6. 架構決策

### 6.1 不為條文計數導入 Graph Database

「法規有幾條、最高條號、修正日期」屬於精確聚合事實，使用既有 Supabase/PostgreSQL 比 Graph Database 更直接、可驗證且維護成本較低。

Graph Database 只在未來需要大量多跳關係時再評估，例如：

- 條文引用其他條文或其他法律。
- 法規、服務、申請條件與主管機關的多層關係。
- 條文修正前後的版本關係。

### 6.2 採用 PostgreSQL + RAG 混合路由

| 問題類型 | 建議處理方式 |
| --- | --- |
| 有幾條、修正日期、最高條號 | PostgreSQL／Structured Record 精確查詢 |
| 某條文內容與白話解釋 | RAG 檢索原文並附官方引用 |
| 條文引用與跨法規關係 | 初期以 PostgreSQL 關聯表處理，複雜後再評估 Graph |

建議資料模型：

```text
law_documents
- id
- law_name
- source_version_date
- official_url
- current_status

law_provisions
- law_document_id
- article_number
- article_suffix
- article_label
- article_text
- effective_from
- effective_to
- is_current
- source_locator
```

其中：

- `COUNT(*) WHERE is_current = true` 回答實際有效條文項目數 72。
- `MAX(article_number) WHERE is_current = true` 回答最高條號 66。
- `article_number` 與 `article_suffix` 分開保存，避免把第 8 條之 1 錯誤排序或漏算。

## 7. 建議新增的 Structured Record

以下只是設計草案，本次未建立正式資料：

```json
{
  "record_type": "law_article_count",
  "source_id": "moj_long_term_care_services_act_20210609",
  "source_version_date": "2021-06-09",
  "highest_article_number": 66,
  "inserted_article_count": 6,
  "effective_article_count": 72,
  "current_status": "current",
  "review_status": "needs_review",
  "official_source_url": "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070040"
}
```

正式實作時應先確認現有 Structured Record schema 與 ENUM 是否已接受 `law_article_count`；若沒有，需建立版本化 schema／ENUM successor，不能只在 runtime 中硬編碼欄位。

## 8. 建議執行順序

1. 確認 agent-runtime 已重新載入 v003 source-family policy，並在 log 看到 policy loaded 與 554 candidates。
2. 執行一般法律 Golden Query，確認「長期照顧服務法是什麼？」能取得至少 3 個有效引用。
3. 建立版本化 `law_documents`／`law_provisions` 或等價 Structured Record schema。
4. 匯入 72 個現行條文項目，保留最高條號與增訂條文語意。
5. 新增精確查詢 intent：`有幾條`、`總共有多少條`、`最後一條`。
6. 新增 Golden Query，驗證答案同時表達「最高條號 66、實際條文項目 72」。
7. 完成 staging regression、citation、安全與 no-data 測試。
8. 驗證通過後，再由 owner 決定是否同步 Structured Record 與 v004／v005 登記到 Google Sheets 管理表。

## 9. 目前阻擋項目

- v005 Human Source Review：`NOT_COMPLETED`。
- v005 Embedding：`NOT_STARTED`。
- v005 OpenSearch indexing：`NOT_STARTED`。
- v003／Supabase Production approval：`false`。
- Live relevance／ranking Golden Query：尚未完整執行。
- 尚無法規條文總數 Structured Record。
- Google Sheets 管理表尚未登記 v004／v005。

## 10. 本次未執行事項

- 未修改 Google Drive 或 Google Sheets。
- 未修改 Supabase 資料或 release 狀態。
- 未建立 Structured Record、資料表或 migration。
- 未變更 `retrieval_eligible`。
- 未啟用 Production。
- 未執行 live Golden Query 或 Playwright QA。
