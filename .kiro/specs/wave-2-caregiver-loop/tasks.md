# Implementation Plan: Wave 2 Caregiver Loop

## Tasks

- [x] 1. 完成 US-C04 人工正式待辦第一切片
  - [x] 1.1 固定 aggregate、scope、狀態機、醫療紅線與 self-assignment 邊界
  - [x] 1.2 實作 additive migration、ORM、repository、service、API、idempotency 與 minimal outbox
  - [x] 1.3 同步 JSON Schema、OpenAPI、examples、static/live contract 與 DIVERGENCE
  - [x] 1.4 實作照護者建立／清單／狀態更新 UI 與 zh-Hant／en 字串
  - [x] 1.5 套用 development migration，完成 full test、build 與 390／768／1024／1280 視覺 QA
  - _Requirements: R1_

- [x] 2. 完成 US-F02 候選行動建議
  - [x] 2.1 定義 Candidate schema、狀態、reason/source/due 與 reject/exclude reason
  - [x] 2.2 實作 deterministic allowed-action／medical-boundary gate
  - [x] 2.3 實作 proposal-only Agent path，不允許直接 formal write
  - [x] 2.4 實作照護者採納／拒絕 UI，採納後才呼叫 R1 formal create command
  - [x] 2.5 補 contract、cross-scope、zero-side-effect、red-team 與 visual evidence
  - _Requirements: R2_

- [x] 3. Wave 2 caregiver-loop 第一切片 closeout（PR #32 與 main CI 通過；非整個 Wave 2 完成）
  - [x] 3.1 驗證 C04/F02 end-to-end、replay、concurrency、permission expiry 與 no-medical-action cases
    - [x] 3.1a PostgreSQL-backed HTTP／transaction 驗收：人工 lifecycle、候選採納／拒絕／排除、replay、row-lock concurrency、授權過期、跨範圍與 medical proposal 零副作用（34 個新案例；CI run `34097721039` 的 142 integration／19 migration tests 與 aggregate 全部通過）
    - [x] 3.1b 真實登入與 Browser → BFF → Core caregiver workflow E2E：2026-09-07 已執行 lifecycle／replay／stale-tab／expiry QA；失效後舊畫面與登入入口文案兩項問題已修正，production rebuild 後另建隔離 campaign 重驗 create/adopt 404 即清除內容，前端 315 tests／typecheck／lint／build 通過（見 `docs/project/wave2-browser-qa-20260907.md`；本機證據，未宣稱新 CI）
    - [x] 3.1c 真實 Agent-to-database 全鏈路：2026-09-08 real-auth BFF → Core → Gemini Runtime → NEEDS_REVIEW Event → 人工 VERIFY → Candidate → UI 採用 → OPEN self-assigned action 全部完成。修正 datetime JSONB 與 VERIFY updated_at 兩個 500；同 key 重送 200、短期 membership 失效後重送 404，來源版本/hash 一致。Core unit 1176 passed；新 DB regression 已隨 PR #32 通過 run `34183906570`，合併後 main run `34184219797` 亦通過。見 `docs/project/wave2-agent-chain-qa-20260908.md`
  - [x] 3.2 更新 traceability 與 Story Map 狀態；C04/F02 第一切片已結案，其他 Wave 2 backlog 與 production readiness 分開追蹤
  - _Requirements: R1, R2_

## US-C01 居服服務紀錄增量（2026-09-11）

- [x] 可選「提交紀錄並完成服務」單一交易 API、最小 receipt 與 exact-assignment gate
- [x] 中英文勾選／二次確認、重試鎖定與完成／拒絕後清除內容
- [x] 本機 unit、static/live contracts、production build 與七組尺寸 synthetic Browser QA
- [x] Disposable PostgreSQL：新增 9 個 rollback／concurrency／exact-scope integration cases 已在 PR #42 CI 通過；完整 DB gate 為 20 migration／177 integration
- [x] PR／CI：PR #42 已於 2026-09-14 合併（`4c56035`）；PR run `34564617822` 與 main run `34796372613` 全部 10 jobs 成功
- [x] real-auth Browser → BFF → Core → DB write E2E：2026-09-14 合成 reader 經 UI 提交並完成，201＋正式 v1／派案 v3／兩筆 outbox 已核對；見下方 real-auth report
- [x] 上次服務紀錄：Owner 核准同 tenant／care unit／elder 跨 worker 交接、獨立 history scope、人工原文；Core／UI／contract 已實作

此增量不代表完整 US-C01 或 Wave 2 完成；證據與下一切片提案見
[Service record completion report](../../../docs/project/service-record-completion-20260911.md)。

## US-C01 上次服務紀錄增量（2026-09-14）

- [x] 更新 Spec 02／05／07，限定服務開始後的本次派案授權，不回填既有 scope
- [x] Core 有界來源查詢、live reauthorization、刪除 gate、strict contract 與本機 unit
- [x] 雙語按需展開、空／失敗／重試、30 秒重驗、隱藏／到期／拒絕清除與延遲回應隔離
- [x] Production build synthetic Browser QA：14 組 viewport／state，七組雙語尺寸與空／錯誤／載入／拒絕／無 scope／鍵盤／reduced motion
- [x] PR #44 已合併為 `4556e57`，main CI `34813366993` 成功；PR CI `34811244713` 全部 10 jobs 成功：20 migration／204 integration，含 27 個新增案例
- [x] real-auth 跨 worker 交接 E2E／隔離 development scope grant：兩個新 synthetic 帳號、四小時上限，交接讀取與負向 gate 通過，最後 writer 撤權後 401 即清除畫面；全部測試憑證與 membership 已撤銷
- [ ] production activation／runtime least privilege／正式 retention 與 note deletion

證據與限制見 [Previous service record report](../../../docs/project/previous-service-record-20260914.md)。
真實讀寫與撤權證據見 [Real-auth report](../../../docs/project/previous-service-record-real-auth-20260914.md)。
QA 環境診斷造成的 development 驗證設定輪替仍另列待辦，不隨功能驗收勾選完成。

## US-C01 居服工作台整合（2026-09-14）

- [x] 今日行程直接開啟指定派案；單筆 GET 改為 exact-assignment live gate
- [x] 開始後同頁按需交班及有界、同派案授權的唯讀待辦
- [x] 提交紀錄並完成後清除內容、重新取得行程；同頁／跨分頁 invalidation
- [x] Core unit 1,408／Frontend 594／lint／typecheck／build／static＋live contracts
- [x] 7 組尺寸完整 synthetic Browser 流程＋7 種 en 390 狀態與像素檢查
- [x] PR #46 程式版本 `44d87ca` 通過 CI `34830767622` 全部 10 jobs；20 migration／212 integration，含新增 8 個 DB cases
- [ ] 新工作台的 real-auth E2E／production activation

詳見 [工作台整合紀錄](../../../docs/project/home-care-workbench-20260914.md)。
