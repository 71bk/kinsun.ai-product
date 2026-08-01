---
inclusion: always
---

# Repository Structure

```text
kinsun.ai/
├── .kiro/                 Kiro specs、steering 與 hooks
├── apps/                  前端應用殼；技術選型尚待決策
├── contracts/             OpenAPI、JSON Schema、valid/invalid examples
├── data/                  資料相關資產邊界
├── docs/                  產品、domain、security、architecture、ADR
├── evals/                 Agent evaluation 與報告
├── infra/                 IaC 邊界；工具尚待決策
├── ops/                   維運資產
├── scripts/               Contract 與 repository 驗證腳本
├── services/
│   ├── core-api/          正式 Domain Core 與 API
│   └── agent-runtime/     受控 Agent Runtime
└── tests/                 跨服務測試邊界
```

完整結構與工作方式：
#[[file:AGENTS.md]]
#[[file:README.md]]

## 分層規則

- API route 只處理 HTTP 邊界、呼叫 service 並包裝 envelope。
- Service 協調 domain、policy、repository 與 outbox，不組裝 HTTP 錯誤。
- Policy 採 deny-by-default，正式授權資料必須由 server-side context 取得。
- Repository 查詢必須明確攜帶 tenant scope。
- ORM model 只負責資料映射；schema 變更由新的 Alembic revision 管理。
- 外部 Provider/SDK 只能出現在 adapter 或 provider 邊界，不散入 domain 與 orchestration。
- Contract 只描述已實作、可實際呼叫的介面；未實作設計放在 `docs/` 或 Kiro Spec。

## 變更同步

- Endpoint 或 envelope 改變時同步 contract、examples、live verification 與 divergence 文件。
- Domain state 改變時同步 migration、tests、traceability 與必要文件。
- 不建立第二份 schema、authorization mapping 或 response mapping 作為競爭權威來源。
