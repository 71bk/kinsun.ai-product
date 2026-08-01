---
inclusion: always
---

# Product Context

kinsun.ai 是 Voice-first 智慧長照 AI 陪伴系統，服務長者、照服員、家屬與照護機構。

完整 repository 規則：
#[[file:AGENTS.md]]

產品範圍與 Persona：
#[[file:docs/01智慧長照 AI 陪伴系統－產品方向與範圍基準 v1.2.md]]
#[[file:docs/01A智慧長照 AI 陪伴系統－使用者研究與 Demo Persona v0.2.md]]

## 核心定位

- 提供陪伴互動、照護流程輔助與經授權的資訊整理。
- 不提供診斷、治療建議，也不取代醫師、護理師或照服員的專業判斷。
- 模型輸出只能是候選、草稿或建議，不能自行成為正式照護事實。
- 先完成可演示且安全的 Gate 1 Vertical Slice，再擴充 RAG、報表與主動陪伴。

## 成功條件

- 長者能以低負擔方式完成語音互動與必要確認。
- 照服員取得有來源、可覆核的資訊，而不是無法追溯的模型結論。
- 家屬只能看到正式發布且位於 Family Share Scope 內的內容。
- 任何功能都不能以跨 tenant、跨 elder、繞過同意或人工確認換取互動率。
