# RAG 路由與檢索品質：2026-09-30 實作紀錄

本次完成可回滾的 Core 路由、120 題離線評測與 40 組真實檢索比較。
目前**不通過檢索品質上線門檻**；既有 PostgreSQL FTS／trigram + Google dense
embedding Hybrid 保留，沒有加入 learned sparse embedding、RRF runtime 或 reranker。
兩個新功能旗標均預設關閉，未修改實際 `.env` 或切換運行中的服務。

## 實作與邊界

1. `knowledge_router.py` 回傳 purpose、reason code、version；涵蓋口語尋求照護資源、
   明確法規查詢、拒絕搜尋、私有紀錄與醫療／注入安全路徑。僅使用有上限的規則，
   沒有新增模型分類呼叫。未知意圖保留既有陪伴路徑，不推定新的權限或 consent。
2. `KNOWLEDGE_ROUTER_V2_ENABLED=false` 完整退回舊分類器。Core 記錄決策代碼，
   不記錄輸入文字。知識回合不帶 Confirmed Memory、Verified Care Events、Care Profile，
   也不啟動 Personal Memory capture；一般語音記憶擷取原有授權證據測試仍保留。
3. `RAG_QUERY_NORMALIZATION_ENABLED` 控制 V2 法規查詢的全形／中文數字／條之號正規化。
   原始使用者訊息不變，兩路檢索使用同一個正規化查詢；不支援的格式保留原文。
   本輪實測未改善整體排名，維持關閉。
4. PostgreSQL 只抽出參數綁定方法；正式查詢 SQL、權重、0.7 分數門檻、554 筆 policy pool、
   最終 3–5 筆引用契約均未改。比較工具在程式外重播候選排序，不把診斷候選交給 Agent。
5. 新增離線 CI 路由品質門檻、資料／指標驗證與 ranking replay 測試；`evals/rag/` 會觸發 RAG jobs。
   沒有新增 CI 付費 API 呼叫、資料庫 migration 或個資 fixture。

## 可重現結果

執行方式與限制見 [評測說明](../../evals/rag/README.md)。報告記錄 HEAD、輸入／實作雜湊、
Python、embedding profile、release、policy；儲存資料為 v004，回覆引用由 policy 映射為 v003。

### 路由

[120 題完整報告](../../evals/rag/reports/routing-v1.json)：40 個語意群組，每組 3 個改寫。
81 題 development／39 題 holdout，同一組不跨 split。題目與標記為合成回歸資料，
尚未由獨立人員覆核，也不是盲測或真實使用者樣本。

| 指標 | 舊分類器 | 新分類器 |
|---|---:|---:|
| 正確 purpose | 84/120（70%） | 120/120（100%） |
| 知識需求有進知識路徑 | 45/72（62.5%） | 72/72（100%） |
| 非知識誤送檢索 | 9/48（18.75%） | 0/48 |

此結果支持把 v2 交付為可切換候選；不能用來宣稱真實意圖理解已達 100%。
目前沒有證據需要再加入付費語意分類器；後續用獨立口語樣本確認規則不足時再評估。

### 真實檢索

[40 組報告](../../evals/rag/reports/live-retrieval-v1.json)：每組第一題，角色為家屬，
Google query embedding + Supabase development 唯讀，共 46 組不同查詢向量、0 次回答生成。
每一題的基線候選重播皆與正式 backend 的排序一致。兩輪前置實測各用了 46 次 embedding；
第一輪的階段 ID 計算修正後已重跑。最終報告使用這 46 組快取，新增 embedding 呼叫為 0；
報告內的 `embedding_calls` 是該次執行量，不是整段工作的累計量。

22 題具備人工待覆核的法條 evidence anchors；以下是 **anchor 指標**，並非完整相關性
Recall@5/NDCG@5，也不等同答案正確率。

| 比較方式 | Anchor recall@5 | Anchor NDCG@5 |
|---|---:|---:|
| 現行 Hybrid | 27.27% | 0.256 |
| Dense 單路 | 25.00% | 0.238 |
| Lexical 單路 | 13.64% | 0.080 |
| 50:50 Hybrid | 27.27% | 0.256 |
| 原始分數門檻 + Hybrid | 27.27% | 0.256 |
| 原始分數門檻 + RRF | 27.27% | 0.163 |
| 法條正規化 + 現行 Hybrid | 27.27% | 0.250 |

22 題的 anchor 都在最多 100 筆候選聯集中，候選 anchor recall 為 100%。
其中 11 題的 anchor 全在分數門檻階段被排除；另 5 題有相關 anchor 通過分數與治理，
但只剩 1–2 筆，因最低 3 筆規則回 `NO_DATA`。6 題指定法條均保留目標法條。
因此本批樣本顯示瓶頸是候選之後的 admission／最終回覆規則，不能據此要求換成 sparse encoder。

40 題中基線有 7 題成功：6 題法條 + 1 題申請長照。申請題未有完備相關性標記，
成功回傳不能當作回答正確。營養題為 `NO_DATA`；v004 中營養／申請說明原始文件仍有治理封鎖，
不能為提高分數而解除。單一離題查詢通過 `NO_DATA`，不足以驗收規格中的 95% no-data 指標。
報告的延遲只有 embedding（跨策略共用快取）與診斷 SQL，不是語音或回答端到端 SLO。

## 依實測收斂的下一個變更

依現行 Spec 20／ADR 0017、0018，先保留受治理的 PostgreSQL Hybrid data plane。
下一個可獨立 review 的工作是「答案充分性與 admission 校準」，順序如下：

1. 以本次漏答題建立完整 graded qrels，補近領域但無答案的負例；由人確認單一法條是否足以回答。
   評測其他三個 audience，使用獨立口語題驗證；不以本次 development/holdout 持續反覆調參冒充新測試。
2. 把 ranking score 與 evidence admission 分開校準。只在 development 選定門檻，再用獨立樣本驗收；
   記錄誤答、漏答、每階段淘汰與延遲，不只追求更多 SUCCESS。
3. 若單一完整引用足夠，提出 1–5 筆的明確充分性規則，同步調整 Spec 20、兩版 retrieval schema、
   Pydantic、fallback、prompt／citation handling 與契約測試；不可只刪掉 `len(results) < 3`。
4. 對保留的證據進行回答生成與逐項 claim/citation 覆核，才驗收 grounded ≥95%、unsupported ≤2%。
   對應 labels 未覆核前，不用自動評分冒充正式通過。
5. 完成上述品質門檻與瀏覽器驗收才考慮預設啟用。需要開放被封鎖來源時，另建 v004 successor
   並走逐項治理 review；本次沒有 production 或外部 activation 授權。

目前沒有證據支持 RRF 或法條字形正規化直接取代現行排名；兩者保留為可重跑實驗。
Sparse／reranker 只在 admission 修正後仍有召回或排序缺口時，再增加比較。

## 驗證狀態

- Agent 全套：599 passed。
- Core 全套：1676 passed；一個既有 Hypothesis deadline 發生 346.94 ms / 200 ms 時限波動，
  單獨重跑 1 passed。最終路由／記憶隔離／評測相關 72 項全部通過；沒有修改既有授權
  property test 的時限或語意。
- Core／Agent Ruff check 與 format：通過。
- CI policy：26 passed；未呼叫付費 API。
- RAG governance 全套：331 passed。新增 audit v011 鎖定 147 個 current inputs，
  `quality_audit.py validate` 通過；v009/v010 改為驗證封存歷史，舊 package bytes 不變。
- 最終 40 組 live replay 完成；兩份報告的 implementation hashes 逐一比對目前程式均相符。
- 未執行：共享 development DB 的破壞性 integration teardown、回答生成品質評測、browser E2E、production activation。

所有 release、policy 與歷史 acceptance／manifest 均保持不變；本紀錄不代表 production 批准。

## PR 合併前 CI 修正（2026-10-01）

PR #65 首輪 CI 發現 normalization 測試以 `tests.unit.*` 引用另一測試檔，
從 repo root 執行時無法 collection。已改為測試內的合成 fixture，維持真實 HybridSearch
及兩路查詢正規化 assertion。既有收案前端測試改為等待 dialog 關閉 effect 完成。

current byte attestation 改為 audit v012，包含 149 個 inputs；v011 package 原封保存，
改作封存歷史。此修正不改動產品檢索、路由或授權行為。
