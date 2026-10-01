# RAG 證據准入比較（2026-10-01）

本輪完成候選快照、人工覆核模板與離線門檻比較工具。尚未選定新的 runtime 門檻，
未更改排序、3–5 引用規則、來源政策或功能開關。完整操作見 [ADMISSION.md](../ADMISSION.md)。

## 實際完成

- 44 題合成問題：原 24 題知識題、8 題口語改寫、12 題相近但草稿標記為無答案的問題。
- 30 題 development、14 題 holdout；同語意群組不跨 split。新題仍由同一實作者撰寫，
  不能描述為獨立盲測。
- 四種 audience 共 176 次唯讀 staging 檢索，所有 baseline 搜尋及最終引用 IDs 均重播一致。
- 20 次新 embedding、0 次回答生成、0 次 DB 寫入。其餘查詢重用既有向量快取。
- 快照涵蓋 149 個不同 evidence chunks；44 題共有 2,899 個待填 pooled qrel slots。
  四角色共有 176 個待覆核 answerability／sufficiency decisions；目前人工覆核數為 0。
- 舊報告的 16 題漏答案例已整理為[逐題閱讀稿](../review/admission-missed-cases-v1.md)。

## Development 比較

以下每個方案共 120 個 audience/query trials，來自 30 題；四角色結果相同，
不能把它們當成四倍獨立樣本。排序始終使用原本 Hybrid 分數。

| 證據准入規則 | SUCCESS | 草稿 anchor recall@5 | 草稿負例證據接受率 | 僅剩 1–2 筆 |
|---|---:|---:|---:|---:|
| 現行：Hybrid ≥0.7 或 raw vector ≥0.7 或 raw lexical ≥0.7 | 36/120 | 25% | 16/36（44.44%） | 20 |
| raw vector ≥0.50 或 raw lexical ≥0.70 | 116/120 | 95% | 32/36（88.89%） | 0 |
| raw vector ≥0.60 或 raw lexical ≥0.70 | 104/120 | 85% | 28/36（77.78%） | 12 |
| raw vector ≥0.70 或 raw lexical ≥0.70 | 28/120 | 20% | 12/36（33.33%） | 20 |
| raw vector ≥0.80 或 raw lexical ≥0.70 | 28/120 | 20% | 12/36（33.33%） | 0 |

本批樣本把 raw lexical floor 改為 0.50 亦得到相同結果，完整九組方案見
[comparison JSON](admission-comparison-v1.json)。這不表示不同分數尺度可以通用同一門檻。

降低 raw vector floor 能挽回草稿 anchor，但同時讓更多草稿負例取得三筆以上證據。
單看 SUCCESS 或 anchor recall 不足以選定方案。所有 reviewed error／Recall／NDCG
指標目前均為 null，因為尚無獨立人工標記。

這是強制進入檢索的診斷。部分個人資料問題在真實應用中會先由 router 阻擋；
表中的負例接受率不是實際誤答率，也沒有執行生成來判定答案是否幻覺。

## Holdout 與下一個人工步驟

Holdout 只跑現行 baseline：56 個 audience/query trials，20 SUCCESS、16 INSUFFICIENT、
20 NO_DATA。草稿 anchor recall 為 40%；12 個草稿負例 trials 皆未回傳證據。
未對 holdout 搜尋最佳門檻，亦未將這些結果稱為獨立品質驗收。

先覆核 16 題漏答的法條是否真正足以回答，再完成 pooled relevance、各角色 answerability
及最小 sufficient evidence sets。數量不足只代表目前契約阻擋，不能直接推論應開放單筆引用。
完成 development 覆核並選定可接受的誤接受率後，才能凍結候選參數，交由獨立題庫驗證。

本輪沒有足夠證據採用任何新門檻；Sparse Embedding／reranker 的新增比較仍待這個缺口釐清。
