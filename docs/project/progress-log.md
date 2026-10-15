# 進度紀錄（AI 協作摘要）

整理日期：2026-10-15。原本記在根目錄 AGENTS.md／CLAUDE.md 頂部的日期紀錄移到此處，新到舊排列。每筆只留結論與
未完成事項，完整證據看連結報告；歷史紀錄不代表目前版本仍通過，現況以當次命令輸出為準。新的交付在此加一筆，
不要寫回 AGENTS.md。

| 日期 | 摘要 | 未完成／限制 | 文件 |
| --- | --- | --- | --- |
| 2026-10-15 | 通知單次 CLI `services/notification-worker/run_daily.py`：預設 dry-run、明確工作時間、有限重試、PARTIAL_FAILURE 非零退出；通知端點改用短效 `ksvc1`＋durable nonce，Core 從 server-configured actor 重查 membership；每次 retry 新 nonce。1960 Core 完整、115 定向、29 CI 規則、契約／lint／format 通過 | HMAC profile 禁用 production、未延長 ADR 0009；未啟用 flags、未 provision 真實服務身分、未發 LINE、未部署 scheduler、未提交 | [排程入口](line-notification-scheduler-20261015.md) |
| 2026-10-15 | 家屬 LINE 通知設定第一切片：`/family/notifications`＋本人 GET／PUT，各授權家屬自行 opt-in；版本／scoped idempotency／outbox、同意與 DAILY／ALL 關係重驗；head `a1c3e5f7b902`、70 業務表 | Core 完整回歸有既有 Hypothesis timing failure（獨立重跑通過，不可寫成一次全綠）；未啟用推播、未部署 scheduler | [交付](family-line-notification-preferences-20261015.md) |
| 2026-10-13 | 真實公開問答驗收：CA07 grounded JSON 截斷，改 4096 token 下限；BFF 34／35（1 題 CITATION_REJECTED）；修正後表格 8 題 5 SUCCESS／3 NO_DATA | 各輪不可合併成新分數；真人語音、人工品質、production 未驗收 | [報告](live-acceptance-20261013.md)、[真人語音清單](../runbooks/manual-voice-acceptance.md) |
| 2026-10-08 | Markdown 整理：移除 11 份無引用 PR 草稿與 5 份退役 Kiro 文件，保留[舊架構](../../.kiro/specs/elderly-care-ai-companion/tasks.md)與[舊登入](../../.kiro/specs/role-based-login/README.md)退役入口 | 退役內容不得作為進度或授權依據 | [整理報告](project-organization-20261008.md) |
| 2026-10-08 | Windows worktree 清理流程（Junction、程序工作目錄、保存未提交資料） | 操作規則見 [本機開發](../runbooks/local-dev.md) | — |
| 2026-10-07 | 訓練時數診斷：原題課名不在來源，NO_DATA 合理；v2 題集 8 題；PR #74 合併（`628015a`） | 固定 16 題未重算；needs_review | [診斷](rag-training-diagnostics-20261007.md) |
| 2026-10-07 | development 啟用 `knowledge-v009-5046fa3d59c4`（713 筆），公開問答期限分層，BFF 24 項通過 | provider 504 一筆；production 未啟用 | [v009](rag-v009-rollout-20261006.md) |
| 2026-10-06 | 55 筆 PDF 版面來源修整為 54 單位；生成模型升 `gemini-3.8-flash`（LOW thinking） | — | [版面](rag-pdf-layout-repair-20261006.md)、[模型](gemini38-upgrade-20261006.md) |
| 2026-10-05 | PR #69 家屬公開問答、#70 專業公開問答；#67／#68 V3 檢索引用與 `rag_v3_failure` 診斷；文字陪伴提示區分資料不足／服務失敗／安全拒答；development 切 v008 | 初測兩筆生成備援原因未確認 | [檢索與引用](rag-retrieval-and-quotes-20261005.md)、[家屬](family-public-knowledge-20261005.md)、[專業](staff-public-knowledge-20261005.md) |
| 2026-10-02 | RAG 簡化 1–4 批；授權匯入 v008（658 筆） | 見 RAG 歷史 | [RAG 歷史](rag-release-history.md) |
| 2026-09-30 | 收案管理 `/staff/enrollments`（head `f0b2c4d6e879`）；長者資料維護七條 API（head `e9a1b3c5d768`） | 真人語音延後 | [收案](staff-enrollment-lifecycle-20260930.md)、[資料維護](staff-elder-profile-maintenance-20260930.md) |
| 2026-09-29 | 無帳號長者語音切片（head `d8f0a2b4c657`），真實登入／Supabase／Deepgram／Gemini／Azure 合成音訊兩輪 | 收音為合成 MediaStream，真人未驗收 | [語音切片](staff-assisted-voice-20260929.md) |
| 2026-09-18 | 語音個人記憶（ADR 0023），需 `personal_memory_voice_auto_save=true` | 舊同意不自動升級 | [ADR 0023](../adr/0023-self-stated-voice-memory.md) |
| 2026-09-17 | 個人自述文字記憶分支（ADR 0022），head `b6d8f0a2c435` | 任意語句、日期事件回想不在範圍 | [Demo](personal-memory-demo.md) |
| 2026-09-16 | 指示：PR 標題與說明用英文，與 Owner 對話用繁體中文 | — | — |
| 2026-09-10 | RAG v004 外部同步（71 筆長照法） | needs_review | [RAG 歷史](rag-release-history.md) |
| 2026-09-02 | CDK／AWS deployment profile 退役（ADR 0019）；service identity replay 改 durable；log safety 統一 | — | [ADR 0019](../adr/0019-retire-aws-cdk-deployment-profile.md) |
| 2026-09-01 | Staff-assisted Elder Session 與 Speech→Core request-bound identity（皆預設關閉）；三角色 route group | — | [現況](../architecture/current-state.md) |
| 2026-08-26 | CI Gate 1 啟用 | — | [CI 規則](../runbooks/ci-gate1.md) |
| 2026-08-06 | 刪除 ADR 0007 legacy 後端與 infra；規格只留 `.md` | — | [現況](../architecture/current-state.md) |
