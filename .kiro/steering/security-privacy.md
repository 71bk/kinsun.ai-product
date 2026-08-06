---
inclusion: always
---

# Security and Privacy

安全規格與威脅模型：
#[[file:AGENTS.md]]
#[[file:docs/spec/07智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1.md]]

## 預設姿態

- Deny by default，採 RBAC + ABAC。
- 不信任 request body、query、header 或模型提供的 actor、role、tenant、elder、assignment、
  consent version 或 permission scope。
- 正式讀寫與高風險 Agent Tool 必須由 Core 使用可信 server-side context 重新驗證。
- Cross-tenant、cross-elder、expired assignment、revoked share 必須拒絕並有 negative tests。
- 單一資源的未授權與不存在採一致回應，避免資源存在性探測。

## 資料限制

- Secret、Token、完整 Prompt、完整 Transcript/Audio 不得進入一般 log。
- Contract、錯誤訊息與 family response 不得洩漏 Restricted Data。
- 測試、Demo、Eval 與截圖只能使用 Synthetic 或完成去識別的資料。
- Neptune、OpenSearch、Cache 與 Agent memory 都是 projection/working state，不是授權或
  正式狀態的 Source of Truth。

## 失敗與撤回

- Consent revocation、停止、不要記與不要再提優先於 retry、replay、backfill 和 scheduler。
- 失敗的授權不得產生資料修改、outbox event 或其他副作用。
- Delete/Revoke 後必須防止資料被 DLQ replay、projection rebuild 或 restore 復活。
