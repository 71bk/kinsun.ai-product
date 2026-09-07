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

- [ ] 3. Wave 2 caregiver-loop closeout
  - [ ] 3.1 驗證 C04/F02 end-to-end、replay、concurrency、permission expiry 與 no-medical-action cases
    - [x] 3.1a PostgreSQL-backed HTTP／transaction 驗收：人工 lifecycle、候選採納／拒絕／排除、replay、row-lock concurrency、授權過期、跨範圍與 medical proposal 零副作用（34 個新案例；CI run `34097721039` 的 142 integration／19 migration tests 與 aggregate 全部通過）
    - [x] 3.1b 真實登入與 Browser → BFF → Core caregiver workflow E2E：2026-09-07 已執行 lifecycle／replay／stale-tab／expiry QA；失效後舊畫面與登入入口文案兩項問題已修正，production rebuild 後另建隔離 campaign 重驗 create/adopt 404 即清除內容，前端 315 tests／typecheck／lint／build 通過（見 `docs/project/wave2-browser-qa-20260907.md`；本機證據，未宣稱新 CI）
    - [ ] 3.1c 真實 Agent-to-database 全鏈路另記環境證據；本次 synthetic source fixture 不涵蓋此項
  - [x] 3.2 更新 traceability 與 Story Map 狀態；明確保留 live Agent／VERIFY HTTP 與完整 Wave 2 closeout 未完成
  - _Requirements: R1, R2_
