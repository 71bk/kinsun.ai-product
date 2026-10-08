# 專案資料目錄

整理日期：2026-10-08。保存正式來源、候選、版本、治理與驗收資料；舊版本不等於可刪除的 QA 暫存。

| 目錄 | 用途與入口 |
| --- | --- |
| `rag-chunks/` | [Chunk 與來源](rag-chunks/README.md) |
| `rag-manifest/` | 來源／版本 manifest，與既有來源資料一併保留 |
| `rag-v2/` | [V2 候選、證據與覆核](rag-v2/README.md) |
| `rag-v3/` | V3 候選、governance、policy、preflight 與歷史 audits；見 [RAG 交付索引](../docs/project/README.md) |
| `rag-layout/` | [PDF frozen extraction 與來源關聯](rag-layout/v001/README.md) |
| `rag-rechunk/` | 本機歷史重切 pilot／successor 與血緣材料，未隨目前 Git 版本提交；不設 repository 連結 |
| `seed/` | [合成 seed](seed/README.md) |

本機 embedding cache 與暫存留在 `.rag-work/`，QA 圖片與日誌留在 `.qa/local/`。
保留正式來源、授權、匯入／回退紀錄與人工覆核狀態；評估證據見 [RAG 評估](../evals/rag/README.md)。

本次整理未變更資料 bytes、外部 DB、release、provider 或啟用設定。
