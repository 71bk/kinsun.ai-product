---
inclusion: always
---

# Human Confirmation and Formal State

Domain state 與生命週期：
#[[file:AGENTS.md]]
#[[file:docs/05智慧長照 AI 陪伴系統－核心工作流、狀態機與錯誤恢復 v0.1.md]]
#[[file:docs/06智慧長照 AI 陪伴系統－Domain Model、商業規則與資料生命週期 v0.1.md]]

## 不可繞過的 Gate

- Memory Candidate 未經長者明確確認，不得成為 ACTIVE Memory。
- Event Candidate 未依規格完成人工覆核，不得成為 Verified Event。
- Draft Family Report 未經授權流程發布，不得被家屬、LINE 或 Email 預覽取得。
- Consent、Assignment、Report Publish 與其他正式狀態轉換只能經 Core API Command Gate。
- Agent、模型、Hook、retry、scheduler 或資料修復程序都不得直接繞過上述 Gate。

## Agent 行為

- Agent 可以提出候選、草稿與 Tool Command，但不能自行宣告人工確認已完成。
- 缺少確認時必須停在可恢復狀態，要求明確確認或交由人工處理。
- 拒絕、撤回或停止必須立即生效，不得以「提升體驗」為理由重試或改寫使用者意圖。
- Kiro task 只有在 Acceptance Criteria 與必要測試有證據時才能標記完成。

## 正式寫入

- Aurora PostgreSQL/Domain Core 是正式交易狀態的 Source of Truth。
- 正式寫入與 outbox 必須位於同一交易。
- Projection 只接受已通過狀態、授權、同意與刪除檢查的正式資料。
