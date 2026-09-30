# 設計

- Elder 新增 `profile_version`。既有照護條目的 version、來源、狀態沿用。
- 新增 `elder_profile_change` 專用受限歷史表；baseline audit_record 禁止敏感原文，不能存放前後照護快照。歷史只由有兩項讀取權的照服員讀取，無公開／家屬 API。
- 每次寫入先授權，再鎖定 tenant/elder 列，重新載入及授權，再處理冪等與預期版本。序列化同長者新增條目，最多 20 筆未停用資料。
- Basic PATCH、care GET/POST/PATCH/retire POST、history GET 共七條 operation。歷史與條目皆 cursor 分頁，no-store。
- 照護更正保留舊來源於快照，新版本標記 STAFF_RECORDED / RECORDED；爭議只能停用。停用保留原內容及來源。
- UI 在長者頁提供資料分頁；無其他工作區權限者直接顯示資料維護與協助使用入口。失去授權立即卸載表單及快照。
- migration 僅增加欄位、表與限定回填；共享 DB 不 reset 或 downgrade。回滾測試僅於 disposable DB。
