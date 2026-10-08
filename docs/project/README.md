# 功能與交付文件索引

整理日期：2026-10-08。按主題歸納現有報告，保留原日期、證據與未完成事項。新報告只在其明列範圍內更新舊結論。

## 入門、協作與審查

| 主題 | 文件 |
| --- | --- |
| 本機建置 | [協作者指南](COLLABORATOR_SETUP.md) |
| CI | [實作與量測](ci-pipeline-optimization.md)、[歷史審查](reviews/ci-pipeline-optimization-review.md) |
| 工程修復 | [Code review 修正進度與未完成事項](reviews/code-review-fix-plan.md) |
| 團隊交付 | [B 交付狀態](B-柏成交付狀態.md)、[分支結案](branch-closeout-20260916.md)、[Kiro 開發證據](kiro-development-evidence.md) |
| 前端計畫 | [Stitch 畫面盤點](stitch-frontend-implementation-plan.md) |
| 設計輸入 | [Memory 與 Family Co-Companion brief](../codex_brief_evidence_aware_memory_family_co_companion.md)；決策以 [ADR 0016](../adr/0016-evidence-aware-memory-supported-confirmation-family-visit.md) 為準 |

## 公開知識與目前 RAG 交付

先讀 v009 rollout 與 10-07 診斷修正。舊版資料數、前端副本路徑與啟用狀態是當時快照；
這些交付不代表 production 啟用或人工來源覆核完成。

| 主題 | 文件與摘要 |
| --- | --- |
| Development release | [v009 匯入與回退](rag-v009-rollout-20261006.md)：713 筆資料與向量，保留 v008／v004 |
| PDF 表格修復 | [來源版面與 repair](rag-pdf-layout-repair-20261006.md)：先前候選與來源修復的背景 |
| 訓練時數診斷 | [10-07 修正](rag-training-diagnostics-20261007.md)：採來源實際課名，未支援課名保留 NO_DATA |
| 模型升級 | [Gemini 升級](gemini38-upgrade-20261006.md) |
| 家屬入口 | [家屬公開問答](family-public-knowledge-20261005.md)：固定家屬受眾 |
| 專業入口 | [照服員公開問答](staff-public-knowledge-20261005.md)：固定專業受眾，無個案查詢或寫入 |
| 檢索、引用與提示 | [自然問句與連續原文引用](rag-retrieval-and-quotes-20261005.md)、[路由與檢索品質](rag-routing-quality-20260930.md) |
| 本機整理 | [文件與 QA 清理](project-organization-20261008.md)：前端改由主工作樹啟動，舊副本已移除 |

## RAG 演進與歷史治理

| 主題 | 文件 |
| --- | --- |
| 簡化四批 | [1：退役流程](rag-simplification-phase1-20261002.md)、[2：本機管線](rag-simplification-phase2-20261002.md)、[3：自然問句 Hybrid](rag-simplification-phase3-20261002.md)、[4：真實資料實測](rag-simplification-phase4-20261002.md) |
| 舊版公開檢索 | [檢索方向](rag-v3-public-retrieval-plan.md)、[runtime policy](rag-v3-runtime-policy-integration.md) |
| Metadata 與長照法 | [Metadata 計畫](rag-metadata-correction-plan.md)、[雲端／本機比對](rag-long-term-care-act-cloud-audit-2026-09-01.md)、[治理同步](rag-law-governance-sync-plan-20260909.md) |

E3 逐筆覆核與 successor audit 鏈已退出日常必經路徑；歷史資料保留。
不能把 pending／needs_review 或 AI 判定寫成已人工 verified；退役邊界見簡化第 1 批。

以下未版控材料僅保留在本機歷史目錄，不設 repository 連結，也不作目前實作或驗收權威：

- 准入／successor：`rag-public-admission-fix-20261001.md`、`rag-evidence-successor-20261002.md`。
- E1–E3：`rag-answer-evidence-plan-20261001.md`、`rag-answer-evidence-offline-20261001.md`、
  `rag-answer-evidence-human-review-20261001.md`、`rag-answer-evidence-review-ui-20261001.md`。

## 照護工作台、派案與服務紀錄

| 主題 | 文件 |
| --- | --- |
| Dashboard | [照護行動數](dashboard-care-action-count-20260908.md)、[今日互動](dashboard-interaction-metrics-20260908.md)、[待覆核事件](dashboard-pending-event-review-20260908.md)、[摘要狀態](dashboard-summary-status-20260908.md) |
| 工作台 | [整合交付](home-care-workbench-20260914.md)、[真實登入](home-care-workbench-real-auth-20260915.md)、[今日行程](home-care-schedule-preview-20260909.md) |
| 派案與服務紀錄 | [Core 切片](assignment-service-record-20260909.md)、[輸入介面](service-record-entry-ui-20260909.md)、[提交與完成](service-record-completion-20260911.md) |
| 上次服務紀錄 | [決策提案](previous-service-record-proposal-20260914.md)、[第一切片](previous-service-record-20260914.md)、[真實登入驗收](previous-service-record-real-auth-20260914.md) |
| 事件 B03／B04 | [類型與時間](b03-event-metadata-correction-20260915.md)、[來源篩選](b04-event-source-filter-20260915.md)、[migration](b03-b04-development-migration-20260916.md)、[前端接線](b03-b04-frontend-verification-20260916.md)、[真實驗收](b03-b04-real-auth-20260916.md) |
| 後端缺口 | [Wave 2 核對](wave2-backend-gap-audit-20260915.md) |

## 身分、收案、本人同意與家屬報表

| 主題 | 文件 |
| --- | --- |
| 收案管理 | [收案生命週期](staff-enrollment-lifecycle-20260930.md) |
| 長者資料 | [資料維護與歷史](staff-elder-profile-maintenance-20260930.md) |
| 管理員與照服員邀請 | [邀請 demo 串接](staff-invitations-demo.md) |
| 家屬加入 | [邀請碼與報表](family-invitation-acceptance-20260923.md) |
| 本人同意 | [照護事件同意入口](care-event-consent-20260922.md) |
| 報表與摘要 | [家屬 scope 與摘要](report-scope-summary-workflow-20260917.md)、[照護端日報](staff-family-report-workflow-20260922.md)、[B02 摘要驗收](b02-summary-acceptance-20260916.md) |
| 驗證設定 | [Development 輪替待辦](development-auth-rotation-followup-20260914.md) |

## 語音、記憶與跨角色驗收

| 主題 | 文件 |
| --- | --- |
| 無帳號長者語音 | [照服員協助](staff-assisted-voice-20260929.md) |
| 文字回覆朗讀 | [回覆音訊](text-reply-audio.md) |
| 語音介面 | [隱藏未支援語言](hidden-voice-languages-20260917.md) |
| 個人記憶 | [語音新增](voice-personal-memory.md)、[錄影 demo](personal-memory-demo.md) |
| Wave 2 | [瀏覽器](wave2-browser-qa-20260907.md)、[Agent 閉環](wave2-agent-chain-qa-20260908.md) |
| Demo 驗收 | [第一輪](demo-acceptance-20260921.md)、[跨角色三輪](cross-role-demo-acceptance-20260922.md) |

原始 JSON、授權與驗收附件留在本目錄或正式 `data/`、`evals/` 路徑，索引不改寫其內容。
