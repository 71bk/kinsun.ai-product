# 需求與證據

| 需求 | 實作 | 驗證 |
| --- | --- | --- |
| R1 | ElderEnrollmentService._query／authorize；read／manage 同筆 grant | HTTP 角色／tenant／membership／scope 拒絕；unit 鎖後失權拒絕 |
| R2 | command、IdempotencyRepository、版本／狀態檢查 | HTTP 轉換／422／409／receipt；live BFF 同 key 200+200、不同 key 200+409 |
| R3 | _stop_service、enrollment_gate、assisted repository refresh | SQL session／conversation／assignment 結束；outbox 故障全回滾；恢復後舊 token 拒絕 |
| R4 | 不刪 elder／consent／profile；管理投影不回傳照護原文 | SQL elder ACTIVE、consent GRANTED；恢復 profile 200、結案後 404 |
| R5 | EnrollmentPanel、/staff/enrollments、中英 messages、跨頁 invalidation | Frontend 12 項新增測試；production browser 真實登入流程及 responsive QA |
| R6 | migration f0b2c4d6e879、creator scope、contract schemas／examples | 回滾 dry run、精確回填；development additive upgrade；117 operations verifier |

可重複測試：`tests/integration/test_elder_enrollment_workflow.py`、
`tests/unit/test_elder_enrollments.py`、`EnrollmentPanel.test.ts`、`enrollments/page.test.ts`。
完整執行情境及未驗證項目見 [交付紀錄](../../../docs/project/staff-enrollment-lifecycle-20260930.md)。
