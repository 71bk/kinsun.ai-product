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
  - [ ] 3.2 更新 traceability 與 Story Map 狀態；不得把 C04 first slice 誤記為 F02 完成
  - _Requirements: R1, R2_
