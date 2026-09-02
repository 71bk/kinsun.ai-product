# Design Document: Wave 2 Caregiver Loop

## 1. Canonical flow

```text
Staff Browser
  → Next.js BFF /backend/core
    → Core authorize_elder(care_action:*) + professional-role gate
      → verified/corrected Care Event scope check
        → care_action state + transactional outbox
```

AI Candidate（R2）將來必須停在另一個 proposal/candidate boundary，再由專業照護者採納；不得直接走上述 formal create command。

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

## 3. Security and data minimization

- API 依序執行 active App Session、elder scope、professional role、tenant-scoped repository 與 formal-source validation。
- Elder-self 明確禁止 `care_action:read/create/update`；family scope 不含 Care Action。
- 第一切片拒絕替其他 actor 指派，避免 client-supplied owner 成為權威。
- outbox 只帶 ID、action type、assignee、source IDs、due date、priority、status、version；不帶自由文字。

## 4. UI

- 長者工作區只有在 `care_action:read` 時顯示 Care Action tab。
- 建立表單只列目前載入的 verified/corrected events，送出單一正式來源；Core 仍支援 1–16 個來源。
- 卡片以 icon＋文字＋形狀呈現 workflow status，顯示 reason、source、期限、建立者／負責人語意與 version；不顯示健康分數。
- 完成、延期、取消使用二階段輸入／確認；version conflict 要求重新載入。
- zh-Hant／en 同步，390／768／1024／1280 與 200% text 皆須驗證。

## 5. Executable contract

- Routes：GET/POST `/api/v1/elders/{elder_id}/care-actions`、PATCH `/api/v1/elders/{elder_id}/care-actions/{care_action_id}`。
- JSON Schema、OpenAPI、valid/invalid examples、static validator、live fail-closed probes 與 `contracts/DIVERGENCE.md` 同步。
