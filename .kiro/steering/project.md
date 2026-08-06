---
inclusion: always
---

# 專案規則

本檔**只轉發，不重述**。所有規則以 `AGENTS.md` 為唯一權威。

#[[file:AGENTS.md]]
#[[file:README.md]]

## 為什麼這裡只有轉發

2026-08-06 之前這個目錄有 5 個 steering 檔（`product`、`tech`、`structure`、
`security-privacy`、`human-confirmation`），各自用自己的話濃縮重述 `AGENTS.md`。
結果是兩份 always-loaded 規則開始互相矛盾——`tech.md` 的服務清單漏了 `rag-ingestion`
與 `speech-gateway`，它寫的 core-api 測試指令也與 `AGENTS.md` §10 不同；五個檔的
`#[[file:docs/...]]` include 更是全部斷掉沒人發現。

那 5 個檔已併回 `AGENTS.md`：目錄結構、分層規則與變更同步進 §9，資源存在性探測與
失敗授權無副作用進 §5，Outbox 同交易與 Projection 前置檢查進 §6。

**不要在這個目錄重新寫規則。** 要改規則就改 `AGENTS.md`——一份權威，沒有第二份可以漂。

## Kiro 專屬慣例

- Kiro task 只有在對應的 Acceptance Criteria 與必要測試**有實際證據**時才能標記完成。
- Spec 放在 `.kiro/specs/`。未實作的設計寫進 spec 或 `docs/`，**不得寫進 `contracts/`**
  （`AGENTS.md` §8.2——`contracts/` 的語意是「這個可以現在打」）。
