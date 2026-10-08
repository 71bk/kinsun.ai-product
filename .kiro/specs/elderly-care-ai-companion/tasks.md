# 已退役：智慧長照 AI 陪伴系統舊實作計畫

本 Spec 的 TypeScript／Lambda／Step Functions／DynamoDB 方向已由
[ADR 0007](../../../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)取代。
2026-10-08 移除舊 requirements、design 與 tasks.legacy，保留此退役入口。
歷史完成標記、115/115 測試與 29 Lambdas 不代表目前主線進度，也不得作為 Gate 1 驗收。

目前工作依下列入口：

- [Repository 協作規則](../../../AGENTS.md)
- [產品規格](../../../docs/spec/)
- [Canonical Gate 1](../gate-1-agent-vertical-slice/tasks.md)
- [Core](../../../services/core-api/)、[Agent Runtime](../../../services/agent-runtime/)、[唯一 PWA／BFF](../../../packages/frontend/)
- [可執行契約](../../../contracts/)

歷史文件可由 Git 取回，例如從 repository 根目錄執行：
`git show 48a0ef54448888163fe923adf9a51fd251b7ba40:.kiro/specs/elderly-care-ai-companion/tasks.legacy.md`。
不可恢復執行退役任務或把歷史結果計入目前完成度。
