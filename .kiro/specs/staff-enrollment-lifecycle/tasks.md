# 交付檢查

- [x] Schema、migration、精確 scope 回填與不可變歷史
- [x] API、授權、狀態、版本、冪等及同交易失效
- [x] 中英管理頁、原因／影響確認、衝突與撤權
- [x] SQL／HTTP、live BFF 併發、跨角色／scope／tenant 及撤權回歸
- [x] 靜態／runtime contracts、單元測試、lint、typecheck、build
- [x] Responsive UI QA 與交付／traceability 文件

獨立可拋棄資料庫的完整 migration lifecycle／integration suite 留由 CI 執行；
本機不對共享 development 執行 rebuild 或 committed_session 的 TRUNCATE 清理。
本機使用 rollback-only SQL／HTTP 及限時合成帳號的真實 BFF 併發驗證。
