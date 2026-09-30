# 設計

- ElderEnrollment 新增 version；elder_enrollment_change 保存前後狀態、原因、操作人與時間，
  DB trigger 禁止 UPDATE／DELETE。Domain outbox 不包含姓名或原因原文。
- 管理授權獨立於一般照護存取，暫停後仍可由原建立人讀取／恢復。單一授權關係須同時有
  read 與 command scope，不跨關係合併權限；每次鎖等待後重查 live Actor／會員／單位／關係。
- 寫入先鎖 Elder，再鎖 Enrollment；與 profile 及 handoff issuance 共用序列化邊界。
  收案、session cancellation、assignment cancellation、history、outbox 與冪等 receipt 同交易。
- 一般 staff relationship／assignment query 以 enrollment gate 排除非 ACTIVE 或有效期外收案；
  無 enrollment 的 legacy 路徑保留。家屬關係不因機構結案自動修改。
- GET /elder-enrollments；GET /{id}；GET /{id}/history；POST /{id}/{action}，
  action 僅 suspend／resume／end。所有 API 在 /api/v1 下、no-store、opaque cursor。
- /staff/enrollments 提供獨立管理入口；結案後一般長者工作台拒絕存取。
