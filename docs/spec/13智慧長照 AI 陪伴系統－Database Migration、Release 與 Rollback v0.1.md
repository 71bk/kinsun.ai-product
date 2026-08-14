智慧長照 AI 陪伴系統－Database Migration、Release 與 Rollback v0.1

## 文件資訊

版本：v0.1

狀態：Draft｜Python Backend、Aurora PostgreSQL、事件投影與 Agent Artifact 的發布與復原基準，待 Framework、ORM、Environment 與實測結果校準

建立日期：2026-07-26

文件 Owner：Backend／Platform Owner

審查者：五人團隊

適用範圍：Aurora PostgreSQL、Python Core API、Agent Runtime、Domain Event、OpenSearch、Neptune、S3、Prompt、Policy、Model Route、RAG Corpus、Feature Flag、CI／CD、Backup 與 Restore

## 2026-08-14 Account／Elder Migration Overlay

依 [ADR 0013](../adr/0013-separate-account-elder-enrollment-entitlement.md)／[Spec 17](17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md)，本次 Domain 演進必須採 Expand → Backfill → New-write／Compatibility → Authorization Cutover → Validate → Contract：

- 不重建資料庫、不合併既有 Alembic revisions、不修改 baseline SQL。
- 先新增 `elder_enrollment`、`service_entitlement` 與必要約束；現有 `elder.tenant_id`、`elder.actor_id`、`actor_type=ELDER` 暫時保留。
- Backfill 必須產生 collision／ambiguity report；不得對多 Tenant、重疊 Assignment 或不明付費狀態靜默推斷。
- 新寫入停止「Account 必然建立 Elder」；compatibility fallback 必須可量測、可 feature-flag rollback。
- Contract 只在 fallback 歸零、cross-elder／cross-tenant／expired-enrollment／entitlement／offboarding negative tests 通過後執行。

## 相關文件

08｜AWS 系統架構、服務選型與 ADR v0.1

https://docs.google.com/document/d/136qR8PhU8v-vckak286q_2Ln3otQ0KRExTDvAO3_sAE/edit

09｜Multi-Agent、Agentic Workflow 與 Context Engineering v0.1

https://docs.google.com/document/d/1ZfkKMMW2tfu5nSXn74WncuN6VN2iVVOeJ5kDxMSVr4Q/edit

10｜API、Event、Tool 與 Data Contracts v0.1

https://docs.google.com/document/d/1s2iM5Yue8WdpVa04DmQm-F_jTkHrPVaSW5ZaFFXD1bA/edit

11｜測試策略、Agent Evaluation 與品質門檻 v0.1

https://docs.google.com/document/d/1saeohikZZ63P2ud1YNHMQDKBKX2wgVnMsQ3LPTAD2qY/edit

12｜實作計畫、環境、團隊分工與交付路線 v0.1

https://docs.google.com/document/d/1OGa9igfGHILGPJE3PmvynP23LxA9FPsT8jPO_R-SG9o/edit

# 一、文件目的

本文件定義智慧長照 AI 陪伴系統如何安全地變更資料庫 Schema、資料內容、Python 應用程式、Agent、Prompt、Policy、Contract、Graph、Search Index 與通知元件，並在發布失敗時選擇 Roll Forward、Rollback、Feature Flag Disable、Replay 或 Projection Rebuild。

本文件的核心問題不是「怎麼把舊版本換回去」，而是：

1. 變更是否向後相容？

2. 舊版與新版程式能否同時運作？

3. 已寫入的新資料會不會讓舊版無法讀取？

4. Event Consumer、Graph、Search 與 Agent Context 是否需要重建？

5. Consent、Authorization、Report Published Gate 與資料隔離是否仍成立？

6. 失敗時應回退應用程式、關閉功能、修復資料，還是向前補 Migration？

# 二、核心發布原則

1. Database First，但不是先破壞：Schema 先擴充，再部署可同時讀新舊格式的程式，最後才移除舊欄位。

2. Expand → Migrate → Contract：高風險變更至少分三階段，不在同一版本直接 Rename／Drop。

3. Forward-Only Migration：已套用至共用環境的 Migration 不修改、不重新排序、不重用版本號。

4. Application Rollback 不等於 Database Rollback：應用程式可以快速退版，但資料庫通常以向前修復為主。

5. Single Migration Runner：每個環境只有一個受控 Migration Job 執行 Schema 變更，Web、Worker 與 Agent Container 不自行搶跑。

6. Immutable Artifact：Image、Wheel、Prompt、Policy、Schema、Model Route、RAG Manifest 與 IaC 均以不可變版本發布。

7. Compatibility Window：至少保留前一版應用程式與 Event Consumer 可運作的相容窗口。

8. Projection Is Rebuildable：Neptune、OpenSearch、Cache 與 Agent 長期候選資料不得成為唯一事實來源。

9. Security Gate Before Traffic：權限、Consent、Cross-Elder Isolation 與家屬 Published Gate 未通過，不得切流量。

10. Evidence Before Release：發布必須有 Migration Report、Test Report、Artifact Version、Trace、Rollback Decision 與 Owner。

# 三、Python Migration 技術基準

## 3.1 Framework 尚未定案時

Python Core API 目前維持 FastAPI／Django 待技術決策，因此本文件採兩條相容路線：

• FastAPI／SQLAlchemy 路線：SQLAlchemy 2.x＋Alembic。

• Django 路線：Django ORM＋Django Migrations。

兩條路線都必須遵守相同的版本、相容、鎖定、回填、驗證、Roll Forward 與審計規則。

## 3.2 v0.1 建議

若核心後端採 FastAPI，建議 Repository：

/services/core-api

/app

/domain

/application

/adapters

/api

/models

/migrations

/versions

alembic.ini

若採 Django，Migration 位於各 bounded-context app，但發布仍由單一 Migration Job 統一執行，不允許多個 Container 在啟動時同時 migrate。

## 3.3 Migration 命名

Alembic：revision ID 由工具產生，檔名使用 YYYYMMDD_HHMM_<ticket>_<purpose>.py。

Django：保留框架編號，Migration Name 附 purpose，例如 0012_add_report_version.py。

每個 Migration 檔案需包含：

• Purpose／Ticket。

• Risk Level。

• Estimated Lock／Duration。

• Backfill Strategy。

• Compatibility Requirement。

• Verification Query。

• Roll Forward Plan。

• Rollback Limitation。

• Data Classification Impact。

# 四、Migration 類型與風險分級

## M1｜低風險 Additive

新增 Nullable Column、新 Table、新 Index（非阻塞方式）、新 Enum Lookup Data。

預設可向後相容，但仍需驗證 ORM Default 與讀寫行為。

## M2｜中風險 Behavioral

新增 NOT NULL、Unique Constraint、Foreign Key、Default、資料型別擴充、索引重建。

需分階段、資料掃描與預估鎖定時間。

## M3｜高風險 Transformative

Rename／Drop Column、拆表、合表、主鍵變更、資料加密格式變更、跨 Tenant 重分配、事件欄位語意改變。

不得一次完成；需 Expand／Migrate／Contract、雙讀／雙寫或版本轉接。

## M4｜不可逆或敏感

大量刪除、匿名化、Consent Revocation 清理、PII Tokenization、Audit Retention 清理。

需明確 Approval、Backup、Dry Run、Sample Verification 與不可逆警告。

# 五、Expand／Migrate／Contract 模式

## 5.1 Expand

先加入新結構，不移除舊結構。

範例：將 family_report.content_text 改為 report_version 表。

步驟：

1. 新增 report_version Table。

2. 舊欄位仍保留。

3. 新版程式可讀舊欄位，也能讀新 Table。

4. 寫入先雙寫或由 Outbox 建立新版本。

5. 建立監控：new_write_success、fallback_read_count、data_mismatch_count。

## 5.2 Migrate

以可重啟、分批、冪等方式回填既有資料。

要求：

• 使用 Batch Cursor，不一次載入全部資料。

• 每批有 checkpoint、processed、success、failed、last_key。

• 可安全重跑，不重複建立資料。

• 每批重新檢查 Tenant／Elder Scope 與資料狀態。

• 不將 WITHDRAWN、REJECTED、DELETED 或未確認資料誤轉為有效資料。

• 失敗資料進 Migration Error Table 或受控檔案，不靜默略過。

## 5.3 Contract

確認新版已穩定、Fallback Read 接近零、資料驗證通過後，才移除舊欄位、舊索引、舊 Event Version 與舊 Feature Flag。

Contract 前提：

• 前一版應用程式已不再需要舊欄位。

• Queue 中不存在舊版 Event 或已有 Upcaster。

• Backup／Restore Drill 完成。

• Rollback Window 已關閉或改為 Roll Forward。

• Owner 與 Reviewer 核准。

# 六、資料庫 Migration 執行流程

1. Developer 產生 Migration。

2. Local 空資料庫 migrate up。

3. 從前一版 Schema migrate up。

4. 建立測試資料並跑 Domain／Authorization Test。

5. Static Review：禁止危險 SQL、無條件全表更新、無範圍刪除。

6. CI 啟動臨時 PostgreSQL 執行 Migration Test。

7. Dev Apply。

8. Staging Dry Run：估計 Rows、Lock、Duration、Disk Growth。

9. Staging Apply＋E2E＋Agent／Event／Projection Test。

10. Release Approval。

11. Production／Demo Migration Job Apply。

12. Verification Query＋Application Smoke。

13. Traffic Shift。

14. Post-Release Observation。

# 七、Migration Job

Migration Job 使用與 Core API 相同的程式版本與 Dependency Lock，但使用獨立 Command：

• FastAPI／Alembic：alembic upgrade head。

• Django：python manage.py migrate --noinput。

要求：

• 使用專用 IAM Role／DB Credential。

• 正常 Web／Worker Role 不具 DDL 權限。

• Job 同時間最多一個執行。

• 記錄 migration_version、git_sha、image_digest、started_at、ended_at、result、operator、environment。

• 失敗立即停止部署，不讓新版程式接流量。

• 不在 Container 每次啟動時自動 migrate。

# 八、Schema 版本與應用程式相容

每個應用程式版本宣告：

APP_VERSION

MIN_SCHEMA_VERSION

MAX_TESTED_SCHEMA_VERSION

CONTRACT_VERSION

EVENT_VERSION_RANGE

PROMPT_BUNDLE_VERSION

POLICY_VERSION

啟動時：

• Schema 低於 MIN_SCHEMA_VERSION：拒絕啟動。

• Schema 高於 MAX_TESTED_SCHEMA_VERSION：Staging／Prod 預設拒絕或只進 Maintenance Mode。

• Migration In Progress：需要明確 Maintenance／Compatibility Mode。

# 九、常見 Schema 變更規則

## 9.1 新增 Column

優先 Nullable，不直接在大型 Table 新增高成本 Default＋NOT NULL。

流程：新增 Nullable → 新版寫入 → 回填 → 驗證 → 加 NOT NULL。

## 9.2 Rename Column

不得直接 Rename 後立即部署。

流程：新增新 Column → 雙寫 → 回填 → 雙讀／優先新欄位 → 停止舊欄位寫入 → Drop。

## 9.3 Drop Column／Table

至少跨兩個 Release；先移除程式引用與監控 Read Count，再 Contract。

## 9.4 Enum

資料庫 Enum 或 Python Enum 不直接移除值。

先停止產生、保留讀取、轉換既有資料、確認 Queue／Event 不含舊值後再移除。

## 9.5 Index

高流量環境使用低鎖定策略；新增前確認 Query Pattern，移除前確認 Index Usage。

## 9.6 Foreign Key

先掃描孤兒資料並修復；若歷史資料不完整，不得直接把 Migration 失敗當成資料已正確。

## 9.7 JSONB

JSONB Schema 仍需 schema_version；讀取端支援至少目前版與前一版，背景 Worker 負責升級。

# 十、資料回填框架

Backfill Job 欄位：

job_id

migration_name

resource_type

tenant_scope

cursor

batch_size

processed_count

success_count

failure_count

status

started_at

updated_at

completed_at

error_summary

狀態：CREATED → RUNNING → PAUSED／FAILED／COMPLETED → VERIFIED。

Backfill 規則：

• 預設以主鍵或穩定時間＋主鍵排序。

• 每筆更新使用 expected_version 或條件式更新，避免覆蓋使用者新變更。

• 對大量更新限制每批 Transaction 大小。

• 可 Pause／Resume。

• 寫入 source_version 與 migration_job_id。

• 執行期間監控 DB CPU、Connections、Replica Lag、Lock、Queue Age。

# 十一、Seed Data 與 Reference Data

Reference Data：Role、Event Type、Report Status、Reason Code、Policy Setting 等需版本化。

規則：

• 使用 Upsert 且 Key 穩定。

• 不以顯示文字作主鍵。

• 不自動覆蓋管理者已核准的業務設定。

• Locale Text 與 Code 分離。

• Demo Persona Seed 與 Production Reference Data 分開。

• 林阿嬤、張阿姨、陳伯伯只存在 Demo／Test Environment。

# 十二、Application Release Artifact

Python Backend 發布物：

• Container Image Digest。

• Python Version。

• Dependency Lock Hash。

• Git SHA／Tag。

• API Contract Version。

• Schema Compatibility Range。

• Environment Config Version。

• Feature Flag Defaults。

禁止：

• 使用 latest Tag。

• 部署時才 pip install 未鎖定最新版。

• 同一 Tag 覆蓋不同 Image。

• 手動進 Container 修改程式或套件。

# 十三、Python Dependency Release

• 使用 uv.lock、poetry.lock 或 requirements lock，團隊只選一套。

• PR 執行 vulnerability scan、license check、unit／integration test。

• Major Dependency Upgrade 不與 Domain 大變更綁在同一 Release。

• ORM、Pydantic、Web Framework、AWS SDK 與 PostgreSQL Driver 更新需跑 Contract／Migration／Async Test。

• 安全修補可使用 Fast Track，但仍需 Staging Smoke 與 Rollback Plan。

# 十四、Release Bundle

每個 Release Candidate 建立 Release Manifest：

release_id

environment

git_tag

core_api_image_digest

agent_runtime_image_digest

worker_image_digests

migration_head

contract_version

event_versions

prompt_bundle_version

policy_version

model_route_version

rag_manifest_version

graph_projection_version

search_index_version

seed_version

feature_flags

approved_by

released_at

known_risks

rollback_target

# 十五、發布順序

一般相容發布：

1. IaC Additive Change。

2. Database Expand Migration。

3. Event／Contract Upcaster 與 Consumer Compatibility。

4. Worker／Projection Consumer。

5. Core API 新版。

6. Agent Runtime／Prompt Bundle。

7. Frontend。

8. Enable Feature Flag。

9. Backfill／Projection Rebuild。

10. Observation。

11. Contract Migration（後續 Release）。

理由：Consumer 必須先能接受新版 Event，再讓 Producer 發送新版內容。

# 十六、Deployment Strategy

## 16.1 Hackathon／Demo

採 Rolling 或簡化 Blue／Green：

• 舊版保留可立即切回。

• Staging 固定 Demo Tag。

• Freeze 後只允許 P0／P1 修復。

• 每次切換後跑 10 條核心 E2E 子集。

## 16.2 正式 Target

Core API 優先 Blue／Green 或 Canary：

• 先部署 Green，不接正式流量。

• 跑 Migration Compatibility、Health、Smoke。

• 先切少量流量。

• 監控 Error、Latency、Auth Denied、Consent Block、DB、Queue。

• 符合門檻後逐步擴大。

• 異常時停止擴大並切回 Blue。

## 16.3 Background Worker

避免新舊 Consumer 同時對同一工作產生不相容結果。

可使用：

• Event Version Routing。

• Queue per Consumer Version。

• Feature Flag。

• Leader／Deployment Generation。

• Idempotency Key＋Resource Version。

# 十七、Event Contract Release

## 17.1 Event Envelope

Event Envelope 保留 event_type、event_version、event_id、occurred_at、producer、tenant_id、elder_id、aggregate_id、aggregate_version、trace_id、payload。

## 17.2 相容規則

• 新增 Optional Field：通常相容。

• 改名、刪除、改型別、改語意：Breaking，需新 event_version。

• Consumer 忽略未知欄位。

• Producer 在相容窗口內可持續發送舊版或由 Upcaster 轉換。

• DLQ Replay 前固定 Consumer Version 與 Event Transformation Version。

## 17.3 Consumer Deployment

Consumer 先部署支援 v1＋v2，再讓 Producer 發 v2；待舊 Queue 清空後才停止 v1。

# 十八、Agent、Prompt 與 Policy Release

## 18.1 Agent Runtime

Agent Runtime 以 Image Digest 發布，Agent ID、Agent Version、Tool Schema Version 與 Model Router Version 隨 Release Manifest 保存。

## 18.2 Prompt

Prompt 採 Draft → Evaluated → Approved → Published → Deprecated。

發布前跑：

• Persona Dataset。

• Prompt Injection Dataset。

• Medical Boundary Dataset。

• Cross-Elder Isolation Test。

• Tool Usage Test。

Prompt 回退不代表 Domain State 回退；只切換 prompt_bundle_version。

## 18.3 Policy

Authorization、Consent、Safety 與 Share Policy 分開版本化。

Policy 變更屬高風險：

• 預設 Fail Closed。

• 必須有 Negative Test。

• 可先 Shadow Evaluate，比較新舊 Decision。

• 不與無關 UI 功能一起發布。

## 18.4 Model Route

Model Route 使用設定版本，支援 Canary／Fallback。

更換模型需固定 Prompt、Dataset 與 Policy，避免無法判斷品質差異來源。

# 十九、RAG Corpus 與 Search Index Release

RAG Release Bundle：

source_manifest_version

chunk_schema_version

embedding_model_version

index_mapping_version

review_policy_version

corpus_snapshot_id

流程：

1. 新 Corpus 匯入新 Index／Alias Target。

2. 驗證 Chunk Count、Metadata、review_status、risk_level、source_id、effective_date。

3. 跑 Retrieval Eval。

4. 切換 Read Alias。

5. 保留舊 Index 於 Rollback Window。

6. 觀察後刪除。

禁止直接在唯一 Production Index 原地大量覆寫而無 Snapshot／Alias。

# 二十、Neptune Graph Projection Release

Graph 為 Aurora 正式資料的投影。

Graph Version 包含：

graph_schema_version

projection_code_version

source_event_version

rebuild_checkpoint

變更流程：

• 先讓 Projection Worker 支援新舊 Graph Schema。

• 對新 Label／Edge 採 Additive。

• 大改時建立新 Graph Namespace／Cluster／Snapshot 或加 version 屬性。

• 完整重放 Outbox／Domain Event 建立新投影。

• 比較 Node／Edge Count、Sample Query、Source Coverage、Cross-Elder Filter。

• 切換 Query Adapter。

• 舊投影保留至驗證完成。

Graph 失敗不回滾 Aurora；以停用 graph_retrieval Feature Flag、改查 Aurora／OpenSearch 並重建投影。

# 二十一、Feature Flag Release

Feature Flag 至少包含：

flag_name

version

default

environment

audience／tenant scope

owner

expires_at

rollback_action

使用情境：

• graph_retrieval

• family_notification

• proactive_companion

• custom_asr

• home_care_mode

• new_report_version

規則：

• Flag 不是永久架構。

• 安全規則不可用 Flag 關閉。

• Flag 關閉後資料狀態仍一致。

• 高風險功能預設 Off，逐 Tenant／Persona 開啟。

• Contract Migration 前清理舊 Flag。

# 二十二、Rollback Decision Tree

第一步：是否有資料破壞或安全風險？

• 有：立即停止流量／關閉 Feature、撤銷通知、Fail Closed，啟動 Incident。

• 無：進第二步。

第二步：舊版應用程式能否讀取目前 Schema 與資料？

• 能：Application Rollback。

• 不能：不得盲目退版，改 Roll Forward 或部署 Compatibility Patch。

第三步：問題是否只在 Agent／Prompt／Model／Feature？

• 是：切換 Artifact Version／Model Route／Feature Flag。

第四步：問題是否只在 Projection？

• 是：停用 Graph／Search 路徑、修正 Worker、Replay／Rebuild。

第五步：是否有不可逆資料寫入？

• 是：人工 Data Repair＋Audit，不執行破壞性 Down Migration。

# 二十三、Rollback 類型

RB-01｜Application Rollback

切回前一個 Container Image；前提是 Schema 與 Event 相容。

RB-02｜Feature Disable

最快止血方式；適合 Graph、通知、主動陪伴、新報表格式或新模型。

RB-03｜Configuration Rollback

回退 Model Route、Prompt、Policy、Rate Limit 或 Adapter Config。

RB-04｜Projection Rollback

切回舊 Search Alias／Graph Query Adapter，或重建投影。

RB-05｜Data Repair

使用受控 Script 修復特定資料；需 Dry Run、Backup、Review、Audit、Verification。

RB-06｜Database Restore

僅在嚴重災難或整體資料損毀使用。Restore 會影響所有後續正確寫入，不是一般單一 Release 的第一選擇。

# 二十四、為什麼不依賴 Down Migration

Down Migration 常無法安全還原：

• 新欄位已有新資料。

• Drop／Transform 已失去資訊。

• 外部通知已發送。

• Event 已被多個 Consumer 處理。

• Graph／Search 已產生投影。

• Consent／Deletion 已觸發不可逆處理。

因此正式環境以 Forward Fix、Compatibility Patch、Feature Disable 與資料修復為主；Down 只允許 Local／Test 或確定無資料的 Additive Migration。

# 二十五、Backup 與 Restore

## 25.1 Backup Scope

• Aurora Snapshot／Point-in-Time Recovery。

• S3 Versioning／Lifecycle。

• Neptune Snapshot 或可重建 Event Log。

• OpenSearch Snapshot／Index Rebuild Manifest。

• Prompt／Policy／Schema／Model Route／IaC 在 Git／Artifact Store。

• Release Manifest 與 Audit Evidence。

## 25.2 Restore 原則

• Restore 到新資源，不直接覆蓋原資源。

• 先驗證 Schema、Row Count、Sample Hash、Tenant／Elder Isolation、Consent Status。

• 應用程式連線切換前跑 Smoke／E2E。

• 恢復後重新處理 PITR 時點後的合法 Event，避免重複通知與刪除。

## 25.3 Restore Drill

Staging 至少演練：

1. 建立 Backup。

2. 模擬資料損毀。

3. Restore 至新 Database。

4. 套用必要 Migration。

5. 重建 Graph／Search。

6. 驗證三位 Persona 與 Published Report。

7. 記錄實際 RTO／RPO。

# 二十六、Release Gate

RG-01｜Artifact Gate

所有 Image、Contract、Prompt、Policy、Model Route、Migration、Seed 均有版本。

RG-02｜Migration Gate

空庫、前版升級、回填、驗證、重跑、鎖定與容量測試通過。

RG-03｜Security Gate

Cross-Elder Leakage＝0、Authorization Bypass＝0、Consent Bypass＝0、Draft Report Exposure＝0。

RG-04｜Compatibility Gate

前一版與新版在相容窗口內可讀寫；Event Consumer 支援版本範圍。

RG-05｜Quality Gate

核心 E2E、Agent Eval、ASR、RAG／Graph 與 Resilience 測試達 11 文件要求。

RG-06｜Operational Gate

Dashboard、Alarm、Runbook、Rollback Target、Owner、Backup、Feature Flag 已準備。

# 二十七、Release Checklist

Release 前：

□ Scope、Ticket、Risk、Owner、Approver 已確認。

□ Migration Head 與前一環境一致。

□ Backup／Snapshot 已完成。

□ Release Manifest 已生成。

□ Contract 與 Event 相容檢查通過。

□ Prompt／Policy／Model Eval 通過。

□ Feature Flag 初始值正確。

□ Staging E2E 與 Negative Test 通過。

□ Rollback Decision 已寫出。

Release 中：

□ Migration Job 成功。

□ Verification Query 通過。

□ New Tasks Health Check 通過。

□ Canary Error／Latency／Auth／Consent 正常。

□ Queue、DLQ、Projection Lag 正常。

□ 無跨長者與家屬資料暴露。

Release 後：

□ Release Manifest 寫入。

□ Observation Window 完成。

□ Backfill／Rebuild 狀態正常。

□ Known Issue 與 Feature Flag 更新。

□ Evidence Bundle 完成。

□ 舊 Artifact／Index 保留至 Rollback Window 結束。

# 二十八、Migration Verification

最低驗證：

• Alembic／Django Migration Head 正確。

• Table／Column／Index／Constraint 存在。

• Row Count 與 Null Count 符合預期。

• 重複、孤兒、跨 Tenant Reference 為零或有核准例外。

• Memory ACTIVE 仍只來自已確認版本。

• Family Report PUBLISHED／DRAFT／WITHDRAWN 數量及可見性正確。

• Consent Revoked 對應工作未重新啟動。

• Outbox 未漏寫或重複發布。

• Graph／Search Source Version 可追溯。

# 二十九、資料修復 Script 規範

修復 Script 放在 /scripts/data-repair/<ticket>/，包含：

README.md

analyze.py

repair.py

verify.py

sample-output.txt

要求：

• analyze 預設只讀。

• repair 需 --dry-run 與明確 environment。

• 預設限制 tenant／elder／resource IDs。

• 使用 Transaction、Batch、Expected Version。

• 輸出 Before／After Count，不輸出不必要 PII。

• 至少一位非作者 Review。

• 執行後保存 Script Version、Operator、Reason、Affected IDs Hash 與 Verification Result。

# 三十、Hackathon Implementation Profile

本次必做：

• Python Migration Runner。

• 一個 Additive Migration＋一個 Backfill Demo。

• 前一版 Schema 升級測試。

• Application Image 可退版。

• Feature Flag 可關閉 Graph 或通知。

• Event Consumer Idempotency＋DLQ Redrive。

• OpenSearch Alias 或等價可切換方式。

• Graph Projection Rebuild／Fallback 證據。

• Release Manifest。

• Demo Seed 一鍵重建。

可延後：

• 正式 Blue／Green 全自動化。

• 跨 Region Restore。

• 大規模線上 Schema Change Tool。

• Production 級長時間 Backfill Orchestrator。

不可省略：

• Single Migration Runner。

• Cross-Elder／Consent／Published Gate 驗證。

• 已套用 Migration 不可修改。

• Release Artifact 不使用 latest。

• 失敗時不得手動改 DB 後假裝成功。

# 三十一、ADR

ADR-13-001｜Python Backend 使用框架原生 Migration，流程規則一致

狀態：Accepted。

FastAPI／SQLAlchemy 採 Alembic；Django 採 Django Migrations。最終 Framework 決策不改變 Expand／Migrate／Contract 與單一 Runner 原則。

ADR-13-002｜正式環境以 Forward-Only Migration 為主

狀態：Accepted。

原因：資料與事件通常不可安全逆轉。

ADR-13-003｜Application 與 Database 分離 Rollback

狀態：Accepted。

原因：程式退版快，但 Schema／Data 必須先證明相容。

ADR-13-004｜Consumer Before Producer

狀態：Accepted。

原因：避免新版 Event 先進入不支援的 Consumer。

ADR-13-005｜Graph／Search 使用 Versioned Projection 與 Rebuild

狀態：Accepted。

原因：投影不是正式來源，應可重建與切換。

ADR-13-006｜Prompt、Policy、Model Route 納入 Release Manifest

狀態：Accepted。

原因：AI 行為變化也是正式 Release，不只是程式碼變更。

# 三十二、待決策

1. Python Framework：FastAPI 或 Django。

2. ORM：SQLAlchemy 或 Django ORM。

3. Dependency Tool：uv、Poetry 或其他鎖定方案。

4. Migration Job 使用 ECS Task、CodeBuild、Lambda 或 Pipeline Job。

5. Demo 環境是否使用 Aurora PostgreSQL 或 RDS PostgreSQL 降低成本。

6. Blue／Green、Canary 或 Rolling 的實作深度。

7. Backfill Job 放在 Core Admin Command、Worker 或 Step Functions。

8. Search Alias 與 Neptune Version Namespace 的實作方式。

9. Rollback Window 與舊 Artifact 保存天數。

10. Pilot／Production 的 RTO、RPO 與 Backup Retention。

# 三十三、v0.1 完成判定

□ Python Backend 的 Migration 路線與 Framework 選擇邊界已定義。

□ Expand／Migrate／Contract 與 Forward-Only 原則已定義。

□ Migration Runner、版本、回填、驗證與相容窗口已定義。

□ Application、Event、Agent、Prompt、Policy、RAG、Graph、Search 的發布順序已定義。

□ Rollback Decision Tree 與六種復原方式已定義。

□ Backup、Restore、Replay、Projection Rebuild 與資料修復已定義。

□ Release Gate、Checklist、Manifest 與 Hackathon Profile 已定義。

□ 下一階段可直接建立 Migration Pipeline、Release Workflow 與 Restore Drill。

# 三十四、下一份文件

14｜智慧長照 AI 陪伴系統－Observability、營運與 Incident Response v0.1

14 文件將定義：

• Log、Metric、Trace、Agent Trace 與 Audit 的欄位及資料最小化。

• Dashboard、SLO、Error Budget 與告警分級。

• API、ASR、TTS、Agent、RAG、Graph、Queue、Report、Notification 與 Database 監控。

• On-call、Incident Severity、通報、止血、復原與事後檢討。

• Runbook、DLQ Redrive、Projection Rebuild、Consent／Deletion 失敗及安全事件處理。
