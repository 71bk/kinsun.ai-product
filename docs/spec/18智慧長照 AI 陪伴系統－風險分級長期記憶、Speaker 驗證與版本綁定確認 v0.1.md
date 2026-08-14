# 智慧長照 AI 陪伴系統－風險分級長期記憶、Speaker 驗證與版本綁定確認 v0.1

## 文件資訊

- 版本：v0.1
- 狀態：Accepted Target Product／Domain Baseline｜尚未代表 schema、API、Frontend 或 Runtime 已完成
- 決策日期：2026-08-14
- 文件 Owner：Project Owner／Domain／Safety／Data Governance
- 適用範圍：Long-term Memory Consent、Speaker ownership、risk-tier policy、confirmation、lifecycle、retrieval 與 audit
- 決策權威：[ADR 0014](../adr/0014-risk-tiered-memory-speaker-verification.md)

## 一、目的與權威邊界

本文件把長期記憶的新產品決策轉成可實作、可測試的規格：

```text
一次總體 LONG_TERM_MEMORY Consent
+ deterministic risk-tier Memory Policy
+ Speaker Gate
+ version-bound confirmation
+ retrieval-time final gate
```

本文件在衝突範圍內優先於 01～17 規格、`.kiro/specs`、`AGENTS.md` 與 `CLAUDE.md` 中「所有
Memory Candidate 一律逐筆確認」或「照護者可代長者確認」的舊敘述。它不改變下列既有規則：

- Agent 只能提出不可信 proposal，正式狀態由 Core 擁有；
- Event Candidate 仍須依既有 Gate 由照護者 verify／correct／reject；
- Elder 是 care subject，可沒有 Account，所有個人 Memory ownership 是 `elder_id`；
- Authentication 不等於 Elder Data authorization；
- 正式狀態與 Outbox 同交易，Projection 可重建但不是正式來源；
- Consent revoke、刪除與「不要記／不要再提」優先於 retry、replay、backfill 與 cache。

本文件描述 Target。Current repo 仍是固定早餐習慣 proposal → Care Event VERIFY →
`PENDING_CONFIRMATION` → `ELDER_UI` confirm → `ACTIVE` 的 first slice；尚未完成風險分級、Speaker
evidence、voice confirmation、version-bound confirmation 或 HIGH policy audit。文件更新不得被當成實作完成。

## 二、核心不變量

> No unverified speaker, unconsented memory, high-risk proposal, or stale confirmation may enter trusted memory or Agent context.

具體規則：

1. 沒有有效 `LONG_TERM_MEMORY` Consent，任何 proposal 都不得建立可信 Memory。
2. Session initiator、Speaker、witness、confirmer 與 legal representative 是不同概念，不得由 Role 推定相同。
3. LOW 只有符合所有自動保存條件才可直接 `ACTIVE`；不是 allowlist 命中就通過。
4. MEDIUM 只有長者本人對固定 Candidate version 明確確認後才可 `ACTIVE`。
5. HIGH 不建立 Memory row，也不保存敏感 proposal 原文。
6. Life Event 與 Long-term Memory 分離；一次性或帶時間性的事件不得被永久化。
7. 每次 Context Retrieval 都重新執行 deterministic Gate，不信任 DB status、Graph、Search 或 cache 單一訊號。
8. Agent 可建議 `memory_kind`／risk，但 Core 依 versioned policy 重新決定。

## 三、名詞

### 3.1 Memory Proposal

Agent／Extractor 從本輪內容提出的非正式建議。它不是 Memory、不是事實，也不具任何授權效果。

### 3.2 Trusted Memory

符合當前 Consent、Speaker、risk、verification、lifecycle、tenant／elder scope 且能通過讀取時 Gate 的
current `ACTIVE` Memory version。

### 3.3 Life／Care Event

具有事件時間、來源與覆核生命週期的陳述或發生事項。例如「昨晚沒睡好」。Event 即使被 VERIFIED，
也不自動表示它是長期穩定特徵。

### 3.4 Speaker Verification

證明某段內容由哪位 Elder 說出所需的受控證據。MVP 不等同 voice biometric；可由受控 Elder-only
Session、speaker selection／lock、conversation state，以及必要的 witness evidence 組成。

### 3.5 Witness

Staff／Family 證明「目前回答的是這位 Elder，且 Elder 確實作出該回答」。Witness 不代表 Elder
作成同意，也不自動具有法律代理權。

### 3.6 Candidate Version

MEDIUM proposal 被保存為 `memory_version` 後的不可變確認標的。確認證據只對該 version 與 content
digest 有效。

## 四、Target Flow

```text
Verified-speaker Conversation
        │
        ├── Event Extraction ──→ Care Event Candidate ──→ existing human review
        │
        └── Memory Proposal
                    │
                    ▼
        Core MemoryPolicyService
        Consent + Speaker + Content + Scope + Policy Version
                    │
        ┌───────────┼────────────────────┐
        ▼           ▼                    ▼
      LOW         MEDIUM                HIGH
   all-of pass   fixed candidate      restricted
        │         version               │
        ▼           │                    └─→ minimal policy audit
 ACTIVE Memory      ├─ elder confirms       no Memory content row
                    │      ▼
                    │   ACTIVE Memory
                    └─ reject/defer/ambiguous
                           ▼
                    non-active state

Every Agent Context request
        ↓
Core deterministic retrieval gate
        ↓
Only current trusted Memory versions
```

## 五、總體 Memory Consent

1. 第一次啟用長期記憶前，系統 MUST 以白話說明：用途、可能自動保存的低風險資料、需要逐筆確認的
   資料、禁止保存的敏感資料、保存期限、查看／更正／停用／刪除與撤回方式。
2. Consent purpose 沿用 `LONG_TERM_MEMORY`，保存 `consent_id`、version、policy version、granted by／at、
   effective／expiry／revoked time。
3. Consent 可由合法流程取得，但不因 Staff 代啟動 Session 就視為已同意。
4. Consent 撤回後立即禁止新 proposal 成為 Memory，並禁止既有 Memory 進 Context；實體清理可非同步。
5. 重新同意不會自動復活先前 INACTIVE／DELETED／rejected 的內容。

## 六、Speaker Gate

### 6.1 最小 Speaker states

```text
VERIFIED_ELDER       # 已驗證是指定 elder_id 本人
WITNESSED_ELDER      # Elder 本人發言，另有 witness evidence
UNKNOWN              # 無法確定是誰
THIRD_PARTY          # 可確定不是該 Elder 本人
CONFLICTED           # 證據互相衝突
```

實作 MAY 使用不同 enum 名稱，但語意與 fail-closed 行為不得縮減。

### 6.2 規則

- 只有 `VERIFIED_ELDER` 或符合本規格的 `WITNESSED_ELDER` 可進個人 Memory policy。
- `UNKNOWN`、`THIRD_PARTY`、`CONFLICTED` 不得寫入任何人的個人 Memory。
- Staff／Family／Device 啟動 Session 只建立 initiator evidence，不建立 Speaker ownership。
- 多人或開放空間 Session 在 Speaker identity 未鎖定前，Memory side effect 必須為零。
- Speaker evidence 至少與 `elder_id`、source session／turn、method、verified／witness actor、時間及版本關聯。

## 七、Memory Proposal Contract

Agent MAY 提供：

```text
proposal_id
memory_kind
normalized_content
source_turn_reference
extraction_confidence
proposal_risk_hint
model / prompt / schema version
```

Core MUST 自行補入或導出：

```text
tenant_id
elder_id
source_session / event reference
speaker_verification
consent_id / consent_version
actual_risk_level
policy_decision
policy_version
reason_codes
required_verification
lifecycle / retention decision
```

Agent 的 `proposal_risk_hint` 只供觀測與 eval，不能降低 Core 導出的 risk，也不能啟用 Memory。

## 八、Deterministic Risk Policy

### 8.1 Policy matrix

| Tier | 典型內容 | 寫入結果 | 確認要求 | 可進 Agent Context |
| --- | --- | --- | --- | --- |
| LOW | 明確自述的音樂偏好、興趣、偏好稱呼 | all-of 通過後直接 ACTIVE | 總體 Consent，不逐筆確認 | 通過 retrieval gate 後可以 |
| MEDIUM | 家人關係、固定聯絡習慣、固定作息 | 建立固定版本 PENDING_CONFIRMATION | 長者本人 UI／Voice 明確確認 | 確認且通過 retrieval gate 後可以 |
| HIGH | 健康／疾病／用藥判斷、情緒推估、家庭衝突、財務、未知敏感類型 | 不建立 Memory row | 第一階段不提供 promotion | 不可以 |

### 8.2 `memory_kind` 與 `memory_type`

現有 broad `memory_type` 可保留作 Domain 分組，但風險不得只由它決定。新增或等價表達 constrained
`memory_kind`，初始例示：

```text
LOW candidates:
  MUSIC_PREFERENCE
  HOBBY
  PREFERRED_ADDRESS

MEDIUM candidates:
  FAMILY_RELATIONSHIP
  CONTACT_ROUTINE
  DAILY_ROUTINE

HIGH / restricted:
  HEALTH_INFERENCE
  MEDICATION_JUDGMENT
  MOOD_OR_LONELINESS_INFERENCE
  FAMILY_CONFLICT
  FINANCIAL_INFORMATION
  SENSITIVE_OR_UNKNOWN
```

Allowlist 與實際 tier 是 versioned Core policy，不是 Agent prompt 常數或 Frontend 判斷。

### 8.3 LOW all-of eligibility

LOW 自動保存 MUST 同時滿足：

1. Speaker 是該 Elder 的 `VERIFIED_ELDER`／有效 `WITNESSED_ELDER`；
2. 句子是 Elder 明確第一人稱自述；
3. `memory_kind` 在當前 LOW allowlist；
4. confidence 達到 policy threshold；
5. 無否定、轉述、反問、條件、時間歧義或已過期語意；
6. `LONG_TERM_MEMORY` Consent 有效；
7. tenant、elder、session、source 與 authorization scope 一致；
8. 未命中敏感、衝突或禁止規則。

例：

| 輸入 | 結果 | 理由 |
| --- | --- | --- |
| Elder：「我很喜歡鄧麗君。」 | MAY auto-save LOW | 第一人稱、明確偏好、allowlisted、其他 Gate 仍須通過 |
| Staff：「林阿嬤今天一直聽鄧麗君。」 | 不建立偏好 Memory | 第三人觀察，不能推論喜歡 |
| Elder：「我以前喜歡鄧麗君，現在沒有了。」 | 不 auto-save LOW | 否定／時間轉折 |
| Elder：「我可能比較喜歡老歌吧？」 | 不 auto-save LOW | 不確定／反問語氣 |

任一條件不成立時，Core MUST 依政策轉 MEDIUM、HIGH 或 `NO_MEMORY`，不得以模型直覺補足。

## 九、MEDIUM Version-bound Confirmation

### 9.1 Candidate 建立

MEDIUM 建立 `memory` 與 immutable `memory_version`，狀態為 `PENDING_CONFIRMATION`。至少保存：

```text
memory_id
memory_version_id / version
elder_id / tenant_id
memory_type / memory_kind
normalized content
content_digest
source references
speaker evidence reference
extraction confidence
consent_id / consent_version
policy_version / actual_risk_level
created_at
```

### 9.2 確認證據

確認命令 MUST 帶 expected memory version，Core MUST 重算／比對 content digest，並在同一正式 transition
中保存：

```text
memory_id
memory_version_id / version
content_digest
consent_id / consent_version
policy_version
confirmation_method
elder response intent
speaker evidence reference
witness actor / evidence（如適用）
confirmed_at
idempotency / correlation reference
```

### 9.3 支援方式

- `ELDER_UI`：候選文字／白話摘要與「記住／不要記／稍後」只針對一個固定 version。
- `ELDER_VOICE`：系統讀出候選專屬問題，verified Elder 明確回答；ASR 與 intent 都過 Gate 才確認。
- `WITNESSED_VOICE`：Elder 親自回答，Staff／Family 只見證身份與回答，不是 confirmer 的替代者。

`ELDER_VOICE`／`WITNESSED_VOICE` 不接受一般對話中的模糊「好」回填到最近一筆 Candidate；每次 prompt、
response 與 candidate version 必須直接關聯。低信心、歧義、沉默、答非所問或 timeout 都維持
`PENDING_CONFIRMATION`，不得推定同意。

### 9.4 修改與衝突

- 修改 normalized content MUST 建立新 `memory_version` 與新 digest。
- 舊 confirmation 只屬舊 version，不能繼承。
- 新 version 重新跑 policy；若為 MEDIUM，重新詢問長者。
- 記憶與新 Event／自述衝突時，先停用或建立待澄清版本，不由 Agent 自行判真偽。

## 十、HIGH Restriction 與最小 Audit

HIGH／restricted proposal：

```text
memory row                     = 不建立
memory_version / content       = 不建立
embedding / graph projection   = 不建立
Agent context                  = 不進入
manual promotion in phase 1    = 不提供
```

最小政策 audit MAY 保存：

```text
policy_decision = REJECTED_HIGH_RISK
memory_kind = SENSITIVE
policy_version
source_event_id or source_session_id
speaker_verification_level
consent_version
bounded reason_codes
decided_at
```

禁止保存 proposal 原文、normalized sensitive content、完整 transcript 或可反推出敏感內容的自由文字 reason。
實作優先評估既有 audit／decision infrastructure；只有在無法安全表達與查核時才新增小型 append-only
`memory_policy_decision` table。它不是 Candidate table。

## 十一、Care Event 與 Memory 分離

| 內容 | Event | Memory |
| --- | --- | --- |
| 「昨晚沒睡好」 | SLEEP_STATEMENT，帶昨晚時間 | 不建立「睡眠不好」永久記憶 |
| 「今天早餐吃粥」 | MEAL_STATEMENT，帶今天時間 | 不推論固定早餐習慣 |
| 「我每天早餐都吃粥」 | MAY 有來源 Event／statement | DAILY_ROUTINE，MEDIUM，需確認 |
| 「我很喜歡鄧麗君」 | 不必製造假 Event | MUSIC_PREFERENCE，符合 all-of 可 LOW auto-save |
| 「女兒通常星期日打電話」 | MAY 記錄本次陳述 | CONTACT_ROUTINE，MEDIUM，綁版本確認 |
| 「她看起來很憂鬱」 | MAY 依 Event policy review | HIGH，不建立 Memory |

Event VERIFIED 只代表該 event version 經覆核，不證明它是穩定 Memory。Memory source 可指向
conversation turn／transcript，或在確有 Care Event 時指向 `source_event_id`；不得為了符合舊 pipeline
而製造不自然的 Event。

## 十二、Memory Data Model 最小演進

### 12.1 重用

- 重用 `memory` aggregate 與 `memory_version`；
- 重用 `LONG_TERM_MEMORY` Consent；
- 重用 existing status 中的 `PENDING_CONFIRMATION`、`CONFIRMED`、`ACTIVE`、`DEFERRED`、`REJECTED`、
  `INACTIVE`、`DELETED`；`CONFIRMED → ACTIVE` 必須同一正式 transaction，不能成為可檢索的中間狀態；
- 重用 source／model／policy version、tenant／elder ownership 與 Outbox 基礎；
- 暫不新增獨立 Candidate aggregate。

### 12.2 Target 欄位能力

`memory`／current policy state 至少需要表達：

```text
memory_kind
actual_risk_level
policy_decision
policy_version
verification_level / required_verification
speaker_evidence_reference
consent_id / consent_version
lifecycle_reason
activated_at / deactivated_at / deleted_at
```

`memory_version`／confirmation 至少需要表達：

```text
immutable normalized content
content_digest
source_session / turn / event references
valid_from / valid_to
confirmation_method
confirmed memory_version_id
confirmed content_digest
elder response intent
witness evidence reference
confirmed_at
```

實作可正規化成 confirmation／evidence table 或安全的 typed metadata，但不得用不可驗證的自由 JSON
縮減 invariant。

### 12.3 Lifecycle

```text
LOW proposal ──policy all-of──→ ACTIVE

MEDIUM proposal → PENDING_CONFIRMATION
                 ├─ exact-version elder confirm → CONFIRMED → ACTIVE（同一 transaction）
                 ├─ reject → REJECTED
                 └─ later / ambiguous / timeout → DEFERRED or remains PENDING_CONFIRMATION

ACTIVE ──correction/new content──→ new version + repolicy
ACTIVE ──no longer applicable / consent rule──→ INACTIVE
ACTIVE/INACTIVE ──delete──→ DELETED + tombstone
```

不新增 `DEACTIVATED` 同義狀態。過期以 `valid_to`＋`lifecycle_reason=EXPIRED` 判斷為不可讀，必要時轉
`INACTIVE`，不先增加 `EXPIRED` state。

## 十三、Context Retrieval Final Gate

Core 每次建立 Agent Context MUST 對每一筆候選 Memory 執行 all-of：

```text
same tenant and elder
AND status = ACTIVE
AND requested version = current version
AND LONG_TERM_MEMORY consent currently valid
AND speaker ownership evidence valid
AND risk-tier verification requirement satisfied
AND confirmation（如需要）綁 current version + content digest
AND acceptable consent version + policy version
AND valid_from reached
AND valid_to not expired
AND not inactive / deleted / tombstoned
AND caller has current elder scope
```

不符合任一條件就排除，並只記 bounded reason code。Graph／Search／cache 只能回傳候選 reference；Core
仍需回查正式狀態。Legacy `ACTIVE` row 若缺 speaker、consent、risk 或 verification evidence，預設不能進
Context，除非遷移規則產生可稽核的保守證據。

## 十四、API Target Behavior

本輪不修改 executable OpenAPI。未來 contract 變更至少涵蓋：

- proposal response／internal command 可表達 `memory_kind` 與 extraction confidence，但明確標示
  Agent risk 只是 hint；
- Core policy result 可表達 LOW auto-activated、MEDIUM pending、HIGH restricted／no-memory；
- MEDIUM confirm／reject／defer command 必須攜帶 `expected_version` 與 candidate-specific evidence；
- voice confirm endpoint／command 必須攜帶 source session、turn、ASR result、intent result 與 Speaker evidence；
- Staff witness command 只記 witness，不得單獨觸發 ACTIVE；
- list／detail response 不回傳 HIGH proposal 原文，且不得讓 unauthorized caller 探測其存在；
- retrieval internal API 只回傳已通過 final gate 的 Trusted Memory。

現有 route 名稱可在相容期保留；是否改為 `/memory-proposals` 或新增 voice confirmation endpoint，待
OpenAPI impact review 後決定，不因本文件直接建立平行 API。

## 十五、Frontend／Voice Target Behavior

### 15.1 Memory settings

- 第一次啟用顯示總體 Memory Consent，說明 LOW／MEDIUM／HIGH 行為與撤回方式。
- 可查看 ACTIVE、PENDING、INACTIVE 記憶與來源摘要；HIGH 不建立可瀏覽的候選卡。
- 撤回後 UI 立即停止顯示為可用，清理進度與正式刪除可分開呈現。

### 15.2 LOW

- 不打斷對話逐筆詢問。
- MAY 以非阻斷方式顯示「已記住」及立即更正／不要記入口。
- 顯示不得暗示 Agent 推測內容已被長者確認；只呈現 Core policy 已接受的第一人稱偏好。

### 15.3 MEDIUM

- 每張確認卡只顯示一個固定 Candidate version 與白話內容。
- 支援「記住／不要記／稍後」；按下時帶 expected version。
- 候選已被修改或過期時，舊按鈕不得成功，重新載入新版本。
- 語音提示須讀出候選特定內容，不用一般「要記住嗎？」匹配最近項目。

### 15.4 Staff-assisted／Family-assisted

- UI 明確顯示目前選定 Elder、Session initiator、Speaker verification state。
- Staff／Family 可協助操作與見證，但不能用自己的按鈕取代 Elder consent。
- 只有未來完成合法代理模型後，才可出現「代理同意」操作，且必須與 witness UI 分開。

## 十六、Migration Proposal（不在本輪執行）

### Phase 1｜Expand

- 新增 nullable／相容欄位或正規化 evidence／confirmation 結構；
- 新增 versioned Memory Policy 與 Core deterministic decision service；
- 新增最小 HIGH decision audit 能力，但不存 proposal 原文；
- 舊 API／row 仍可讀，不改寫既有 migration。

### Phase 2｜Conservative Backfill

- 既有 `ACTIVE` 且有長者確認證據：標為 explicit elder verification，綁現有 current version；
- 既有 `PENDING_CONFIRMATION`：標為 unverified；
- 無法可靠分類的既有資料：風險保守視為 MEDIUM，不自動升 LOW；
- 缺 Speaker／Consent／version evidence 的 legacy ACTIVE：不得直接進新 Context，進 quarantine／待補證據；
- 產生完整 backfill report，不合成不存在的長者確認。

### Phase 3｜New Write + Compatible Read

- 新 proposal 全部走 Core policy；
- LOW all-of 才 auto-activate；MEDIUM 固定版本確認；HIGH 零 Memory row；
- Context 改走 final deterministic gate；
- 舊流程僅供相容讀取，不再建立未分類 Candidate。

### Phase 4｜Verify

- 比對同 tenant／elder 數量、狀態、current version、confirmation binding 與 Context 結果；
- 驗證撤回、expiry、修改、replay、projection rebuild、cross-scope 與 legacy row；
- 所有 invariant／security／contract／E2E test 通過後才收緊 constraint。

### Phase 5｜Contract

- 將必要欄位改為 NOT NULL 或建立等價 constraint；
- 移除舊 blanket-confirmation write path 與未綁版本的 confirmation；
- Deprecate 舊 contract，依相容窗口移除；
- 不刪歷史 migration，不直接重建 production database。

## 十七、Acceptance 與 Test Matrix

| ID | Scenario | Expected |
| --- | --- | --- |
| MEM-P01 | 無 LONG_TERM_MEMORY Consent | 零 Memory／activation／Context side effect |
| MEM-P02 | Verified Elder：「我很喜歡鄧麗君」且符合 LOW all-of | ACTIVE，保存 policy／speaker／source evidence |
| MEM-P03 | Staff：「林阿嬤今天一直聽鄧麗君」 | 不建立 Elder preference Memory |
| MEM-P04 | Elder 含否定／過去式／歧義的偏好 | 不 auto-save LOW |
| MEM-P05 | FAMILY_RELATIONSHIP proposal | MEDIUM PENDING_CONFIRMATION |
| MEM-P06 | Elder UI 確認 exact version | 該 version ACTIVE；正式 state＋outbox 同交易 |
| MEM-P07 | Candidate v3 確認後內容改為 v4 | v3 確認不能啟用 v4；v4 重新 policy／確認 |
| MEM-P08 | Elder voice 明確回答、Speaker 與 ASR Gate 通過 | exact version ACTIVE |
| MEM-P09 | Voice 含糊／低信心／timeout | 維持 pending／deferred，零 activation |
| MEM-P10 | Staff 按 witness，但 Elder 未回答 | 不得 ACTIVE |
| MEM-P11 | Elder 回答，Staff 只見證 | 記 Elder response＋witness evidence，可按規則 ACTIVE |
| MEM-P12 | 健康／憂鬱／家庭衝突／財務 proposal | 零 Memory row；只有不含原文的 minimal audit |
| MEM-P13 | Unknown／third-party／conflicted Speaker | 零個人 Memory side effect |
| MEM-P14 | 「昨晚沒睡好」 | MAY Event；不得建立永久睡眠 Memory |
| MEM-P15 | Event VERIFIED | 不自動 promotion 成 Memory |
| MEM-P16 | Consent revoked／expired | 既有 ACTIVE 不進 Context；新寫入拒絕 |
| MEM-P17 | INACTIVE／DELETED／valid_to expired | 不進 Context／Graph response |
| MEM-P18 | Cross-tenant／cross-elder request | 零可用資料且不洩漏存在性 |
| MEM-P19 | Legacy ACTIVE 缺必要 evidence | final gate 排除，不因 status 放行 |
| MEM-P20 | Replay／rebuild／cache 回傳舊 version | Core final gate 排除，不復活 |

零容忍指標：

```text
unverified_speaker_memory_activation = 0
high_risk_memory_row_created = 0
stale_confirmation_activation = 0
invalid_consent_memory_context_inclusion = 0
cross_elder_memory_context_inclusion = 0
witness_substituted_elder_consent = 0
```

## 十八、實作順序

### 必須現在修

1. 以本 Spec／ADR 收斂舊 blanket confirmation 規格與工程指引。
2. 定義 `memory_kind`、Core policy matrix、Speaker evidence 與 version-bound confirmation executable contract。
3. 先建立 retrieval-time final gate，再開啟任何 LOW auto-save。
4. 補齊 HIGH minimal audit 的 retention／privacy review。

### 可以下一階段修

1. LOW auto-save write path 與非阻斷 UI。
2. MEDIUM UI／Voice／WITNESSED_VOICE 完整閉環。
3. Conservative backfill、Graph／Search projection 與 lifecycle job。
4. 大量候選 review、衝突處理與政策營運介面。

### 暫時不要做

- 不新增獨立 Candidate table。
- 不加入 voice biometric。
- 不讓 Staff／Family 以 witness 身份代 Elder 同意。
- 不提供 HIGH 人工 promotion 捷徑。
- 不以 Agent risk、Prompt allowlist 或 broad `memory_type` 當正式政策。
- 不改寫、合併或刪除既有 migration。

## 十九、Traceability

- Product stories：[Spec 02](02智慧長照%20AI%20陪伴系統－使用者故事與驗收條件%20v1.3.2.md) EPIC D
- Story Map：[Spec 03](03智慧長照%20AI%20陪伴系統－Story%20Map%20v1.2.md) US-D01～D04
- Workflow：[Spec 05](05智慧長照%20AI%20陪伴系統－核心工作流、狀態機與錯誤恢復%20v0.1.md) WF-03
- Domain：[Spec 06](06智慧長照%20AI%20陪伴系統－Domain%20Model、商業規則與資料生命週期%20v0.1.md) Memory Aggregate
- Agent／Context：[Spec 09](09智慧長照%20AI%20陪伴系統－Multi-Agent、Agentic%20Workflow%20與%20Context%20Engineering%20v0.1.md)
- Contracts：[Spec 10](10智慧長照%20AI%20陪伴系統－API、Event、Tool%20與%20Data%20Contracts%20v0.1.md)
- Tests：[Spec 11](11智慧長照%20AI%20陪伴系統－測試策略、Agent%20Evaluation%20與品質門檻%20v0.1.md)
- Identity／Accountless Elder：[Spec 17](17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md)
- Gate 1 executable planning：`.kiro/specs/gate-1-agent-vertical-slice/`
