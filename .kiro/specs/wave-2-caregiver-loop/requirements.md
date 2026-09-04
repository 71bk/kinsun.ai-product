# Requirements Document: Wave 2 Caregiver Loop

- 建立日期：2026-09-02
- 狀態：In Progress
- 交付故事：US-C04（關懷待辦與追蹤）、US-F02（照護者候選行動建議）

## 1. Scope and authority

本 Spec 只追蹤 Wave 2 的 Care Action 閉環，不取代 `docs/spec/02`、`03`、`05`、`06`、`07`、`10`、`11`。正式狀態以 Core PostgreSQL 為唯一權威；Browser 只經 Next.js BFF 呼叫 Core。AI output 在人工採納前不是正式待辦。

## 2. Requirements

### R1: Professional-created formal Care Action（US-C04）

1. 專業照護者 SHALL 能從同 tenant、同 elder 且狀態為 `VERIFIED`／`CORRECTED` 的 Care Event 建立正式待辦。
2. Core SHALL 從可信 `ActorContext` 推導 tenant、elder scope、建立者與負責人；第一個切片只允許 self-assignment。
3. Action type SHALL 只允許聯繫長者、聯繫家屬、確認資訊、邀請活動、追蹤與其他非醫療照護工作；不得建立改藥、停藥或診斷型 action。
4. 每筆待辦 SHALL 顯示 title、trigger reason、related event、creator/assignee、due date、priority、status、resolution 與 version。
5. 狀態更新 SHALL 使用 optimistic concurrency、idempotency 與確定性狀態機；完成、延期、取消 SHALL 保存原因，延期另須新期限。
6. 正式寫入與最小化 outbox SHALL 在同一交易內完成；outbox 不得複製 title、description 或 trigger reason。
7. Family／Elder 與無有效照護 scope 的 actor SHALL fail closed，且 unauthorized／nonexistent 不得洩漏資源是否存在。

### R2: Human-confirmed candidate action（US-F02）

1. AI SHALL 只提出查看、確認、聯繫、活動邀請或追蹤候選，並附 reason、source events 與 suggested due date。
2. Candidate SHALL 與 formal Care Action 分離；只有專業照護者明確採納後，Core 才能建立正式待辦。
3. Candidate SHALL 經 deterministic medical-boundary validation；改藥、停藥、診斷或自動修改照護計畫一律拒絕。
4. Candidate reject／exclude SHALL 保存原因，且不得建立正式 Care Action 或 outbox side effect。

## 3. Non-goals for the first C04 slice

- 不由 Agent Tool 自動建立正式待辦；`create_care_action` 維持 blocked。
- 不實作 arbitrary assignee、跨機構轉派、排班或通知。
- 不把優先順序呈現成健康風險或長者排名。
- R2 candidate lifecycle 不屬於當時的 R1 slice；其後已以獨立 proposal/candidate boundary、人工採納與排除流程完成，不能反向視為 R1 的 Agent 自動寫入能力。
