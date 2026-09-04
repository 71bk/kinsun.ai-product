# Design Document: Wave 2 Caregiver Loop

## 1. Canonical flow

```text
Staff Browser
  → Next.js BFF /backend/core
    → Core authorize_elder(care_action:*) + professional-role gate
      → verified/corrected Care Event scope check
        → care_action state + transactional outbox
```

R2 採用獨立的人機邊界：

```text
Agent Runtime deterministic proposal（untrusted、無 scope/source ID）
  → Core 在 CareEventVersion 私下保存 proposal
    → 專業照護者 VERIFY source event
      → Core 重驗 deterministic policy，建立 PENDING_REVIEW Candidate + immutable source snapshot
        → 專業照護者 ADOPT
          → Core 重驗 scope、candidate version 與 exact source version
            → 呼叫 R1 formal create command + transactional outbox
```

`REJECT`／`EXCLUDE` 只保存人工原因並終止 Candidate，不建立正式待辦或 outbox。Agent Tool 仍不得直接走 formal create command。

## 2. Formal aggregate and state machine

- Aggregate：`CareAction`；tenant/elder scoped，`version >= 1`。
- Create：`OPEN`、self-assigned、future `due_at`、1–16 個不重複 formal event IDs。
- Transitions：
  - `OPEN → IN_PROGRESS | COMPLETED | POSTPONED | CANCELLED`
  - `IN_PROGRESS → COMPLETED | POSTPONED | CANCELLED`
  - `POSTPONED → IN_PROGRESS | COMPLETED | CANCELLED`
  - `COMPLETED`、`CANCELLED` terminal
- `expected_version` 不符回 conflict；terminal／postponed 需 resolution；postponed 需 future due date。

Baseline 已有 `care_action` table，但沒有 version；以 additive Alembic revision 補欄位與 positive check，不修改 frozen baseline。

Candidate aggregate 為 `CareActionCandidate`，狀態固定為
`PENDING_REVIEW → ADOPTED | REJECTED | EXCLUDED`。每筆 Candidate 只綁定 VERIFY 當下的 exact
`event_version_id + event_id + event_version`、canonical SHA-256 與 snapshot schema version；來源綁定由資料庫 trigger 禁止 UPDATE／DELETE。

## 3. Security and data minimization

- API 依序執行 active App Session、elder scope、professional role、tenant-scoped repository 與 formal-source validation。
- Elder-self 明確禁止 `care_action:read/create/update`；family scope 不含 Care Action。
- 第一切片拒絕替其他 actor 指派，避免 client-supplied owner 成為權威。
- outbox 只帶 ID、action type、assignee、source IDs、due date、priority、status、version；不帶自由文字。
- Runtime proposal 只允許固定事件／行動配對，且最多一筆；不得攜帶 tenant、elder、actor、consent、session 或來源 UUID。
- Core policy 只允許查看、確認、聯繫、邀請活動與追蹤，拒絕改藥、停藥、診斷、處方或自動修改照護計畫；建議期限必須在未來 30 日內。
- Candidate list／decision 每次都重新檢查 elder scope 與 professional role；採納另以 optimistic version 與 exact source version 阻止 stale binding。
- VERIFY promotion 失敗不回滾人工事件覆核；formal write 只有 ADOPT 能觸發。

## 4. UI

- 長者工作區只有在 `care_action:read` 時顯示 Care Action tab。
- 建立表單只列目前載入的 verified/corrected events，送出單一正式來源；Core 仍支援 1–16 個來源。
- 卡片以 icon＋文字＋形狀呈現 workflow status，顯示 reason、source、期限、建立者／負責人語意與 version；不顯示健康分數。
- 完成、延期、取消使用二階段輸入／確認；version conflict 要求重新載入。
- zh-Hant／en 同步，390／768／1024／1280 與 200% text 皆須驗證。
- AI 建議使用獨立 medical-blue 區塊及「尚未成為正式待辦」文字邊界；採納前可調整 title、due date、priority，且必須再確認。
- Reject／exclude 使用明確原因與 optional notes；提交前不隱藏正式待辦，也不觸發正式清單重載。

## 5. Executable contract

- Routes：GET/POST `/api/v1/elders/{elder_id}/care-actions`、PATCH `/api/v1/elders/{elder_id}/care-actions/{care_action_id}`。
- Candidate routes：GET `/api/v1/elders/{elder_id}/care-action-candidates`、POST `/{candidate_id}/adopt`、POST `/{candidate_id}/dismiss`。
- JSON Schema、OpenAPI、valid/invalid examples、static validator、live fail-closed probes 與 `contracts/DIVERGENCE.md` 同步。
