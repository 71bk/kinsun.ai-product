# 專案文件索引

整理日期：2026-10-08。依主題選擇文件；功能進度與限制請讀相應交付報告，歷史 PASS 不代表目前版本已重新通過。

## 閱讀入口

| 目的 | 文件 |
| --- | --- |
| 第一次接手 | [專案介紹](../README.md)、[協作者建置指南](project/COLLABORATOR_SETUP.md) |
| AI 協作規則 | [AGENTS.md](../AGENTS.md)、[CLAUDE.md](../CLAUDE.md) |
| 功能、修復與驗收 | [交付主題索引](project/README.md) |
| 產品需求與驗收條件 | [編號規格](spec/)；Markdown 為規格權威版本 |
| 已採用的技術決策 | [ADR](adr/)；依狀態與取代關係閱讀 |
| Agent 邊界 | [架構](architecture/agent-runtime-overview.md)、[服務 README](../services/agent-runtime/README.md) |
| 前端樣式與互動 | [設計系統](design-system/MASTER.md)、[前端計畫](project/stitch-frontend-implementation-plan.md) |
| API 與事件契約 | [Contracts](../contracts/README.md)、[差異追蹤](../contracts/DIVERGENCE.md) |
| 部署與營運 | [部署 smoke](runbooks/deployment-smoke.md)、[Outbox delivery](runbooks/outbox-delivery.md) |
| Demo、競賽與協作 | [Demo 素材](demo/)、[競賽準備度](competition/cht-2026/readiness-audit.md)、[交接](handover/)、[分工](ownership/) |
| 知識資料與評估 | [資料目錄](../data/README.md)、[RAG 評估](../evals/rag/README.md)、[語音評估](../evals/speech/README.md) |
| QA 工具與本機產物 | [QA 保留規則](../.qa/README.md)、[合成 fixture 操作](../scripts/qa/README.md) |

## 文件放置方式

- 需求與驗收規則放 `spec/`；技術決策放 `adr/`。
- 功能交付、修復、驗收與實作計畫放 `project/`，透過主題索引串起相關文件。
- 跨專案審查放 `project/reviews/`；保留未完成事項與歷史限制。
- 操作步驟放 `runbooks/`；交接放 `handover/`；介面規則放 `design-system/`。
- 正式資料與評估放 `data/`、`evals/`；QA 截圖、日誌與暫存放 `.qa/local/<topic>/`。
- 索引不複製整份報告，也不將提案、合成結果或歷史驗收寫成 production 已完成。
