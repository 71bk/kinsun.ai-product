# 照服員收案管理

依 ADR 0013／Spec 17；本次為既有無帳號機構長者的單一收案管理，不含跨機構轉移或 Household。

- R1：原收案建立人以 DAYCARE_CARE_WORKER 身分，在有效機構／據點會員及同據點關係下，
  使用獨立 enrollment:read／enrollment:manage；其他角色、長者或 tenant 不得探測資料。
- R2：ACTIVE → SUSPENDED → ACTIVE；ACTIVE／SUSPENDED → ENDED；ENDED 終態。
  每次必要原因（120 字）、expected_version、Idempotency-Key；失敗不寫歷史／outbox。
- R3：暫停／結案同交易停止平板授權、進行中的對話及未完成派案。一般機構照護存取與清單
  重驗收案狀態；恢復不復活舊 token／conversation／assignment，亦不恢復被獨立撤銷的 scope。
- R4：保留長者、帳號、同意、照護紀錄；家屬分享仍依原規則。管理入口提供必要識別與收案歷史，
  不提供照護原文。多筆收案需人工審查，此切片不得以其中一筆恢復整體存取。
- R5：獨立中英收案清單、影響確認、原因、歷史、唯讀、衝突、重試、撤權清除及手機版面。
- R6：新建者預設 scope；既有資料僅以完整原預設、有效收案與建立人授權精確回填，
  不補自訂／縮限權限。機器契約、SQL／HTTP、安全反例、併發與 UI 驗證同步交付。

真人語音驗收仍延後；本功能不代表 production activation、資料可攜或保存／刪除政策核准。
