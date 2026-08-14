# ADR 0014：長期記憶採風險分級、Speaker Gate 與版本綁定確認

- 狀態：Accepted Target Architecture；尚未代表 schema、API、Frontend 或 Runtime 已完成
- 日期：2026-08-14
- Owner：Project Owner／Domain／Safety／Data Governance
- 部分取代：[ADR 0009](0009-gate-1-synthetic-profile-and-service-boundaries.md) 第 7 節「所有 Memory Candidate 必須由長者逐筆確認」
- 不取代：ADR 0009 的 Event 人工覆核、Agent proposal-only、Core authority、Consent、Outbox、Projection 與安全邊界
- 相關：[ADR 0013](0013-separate-account-elder-enrollment-entitlement.md)、[Spec 18](../spec/18智慧長照%20AI%20陪伴系統－風險分級長期記憶、Speaker%20驗證與版本綁定確認%20v0.1.md)

## 背景

現行 Gate 1 實作把每一筆 Memory proposal 都建立為 `PENDING_CONFIRMATION`，再要求長者以
`ELDER_UI` 逐筆確認。這能避免模型直接建立正式事實，但會讓低風險偏好也反覆打斷對話，且無法完整
表達多人場景中的 Speaker ownership、語音確認見證、敏感提案拒絕、內容版本與確認證據的綁定。

新的產品模式同時包含家庭與機構場景。Elder 可以沒有登入帳號，由 Staff／Family／Device 代為啟動
受控 Session；因此「誰登入並開始 Session」不等於「誰說出內容」，也不等於「誰同意保存」。若只用
Actor Role、按鈕操作者或模型推測判斷，可能把第三人觀察寫成長者偏好，或由照服員取代長者作成同意。

此外，Life Event 是帶時間的發生事項，Long-term Memory 是未來可重用的穩定知識。把「昨晚沒睡好」
推成「長期睡眠不好」會把一次性事件永久化；健康、情緒、家庭衝突或財務推測若另存成候選原文，還會
不必要地複製敏感資料。

## 決策

### 1. 一次總體同意，逐筆處理由 Core 風險政策決定

- 啟用長期記憶前，必須有目前有效的 `LONG_TERM_MEMORY` Consent。
- 總體同意不等於所有內容都可保存；每個 proposal 仍須通過 Speaker、ownership、風險、生命週期與
  tenant／elder scope 的 deterministic policy。
- LOW 符合全部自動保存條件時可直接成為可信 `ACTIVE` Memory，不再逐筆詢問。
- MEDIUM 先建立 `PENDING_CONFIRMATION`，只有長者本人對固定 Candidate version 明確確認後才能
  `ACTIVE`。
- HIGH 不建立 Memory row，不進 Context、Graph、Summary 或 Family response。

### 2. Agent 只提案，Core 才決策

Agent MAY 提出 `memory_kind`、normalized proposal、source reference hint、confidence 與
`proposal_risk`，但這些都是不可信輸入。Agent SHALL NOT：

- 宣告真正的 `risk_level` 或 `policy_decision`；
- 確認、啟用、停用或刪除 Memory；
- 以 Prompt、Tool argument 或模型自述略過 Consent、Speaker Gate 或版本檢查。

Core `MemoryPolicyService` MUST 根據 versioned policy、allowlist、Speaker state、Consent、內容特徵、
來源與 scope 重新導出最終決策。安全側欄位只能由 Core 寫入。

### 3. LOW 採 all-of 自動保存條件

LOW 不是只看 allowlist。只有同時符合下列條件才可自動成為可信 Memory：

1. Speaker 已驗證為該 `elder_id` 本人；
2. 內容是長者明確第一人稱自述；
3. `memory_kind` 在 Core-owned LOW allowlist；
4. extraction confidence 達到該 policy version 的門檻；
5. 沒有否定、轉述、反問、條件、過去已失效或時間歧義；
6. `LONG_TERM_MEMORY` Consent 目前有效；
7. tenant、elder、source session 與資料 ownership 全部一致。

例如「我很喜歡鄧麗君」可在政策允許時自動保存；「林阿嬤今天一直聽鄧麗君」只是第三人觀察，不能
推論為「林阿嬤喜歡鄧麗君」。任一條件不成立時不得降級猜測成 LOW；應改為 MEDIUM、HIGH 或不建立。

### 4. MEDIUM 確認綁定固定 Candidate version

MEDIUM 包含會影響未來互動的重要事實，例如家庭關係、固定聯絡習慣與固定作息。確認證據至少綁定：

- `memory_id`；
- `memory_version_id`／candidate version；
- normalized content digest；
- `consent_id`／consent version；
- `policy_version`；
- confirmation method、長者回答、時間與必要的 witness evidence。

任何內容修正都建立新版本，舊確認不得繼承。舊版本即使曾為 `ACTIVE`，也不能讓修改後文字直接進入
Context。新版本須重新經 policy；若仍屬 MEDIUM，必須重新確認。

### 5. 語音確認與見證不混淆

MEDIUM 可用下列方式確認：

- `ELDER_UI`：長者本人操作受控 UI；
- `ELDER_VOICE`：已驗證 Speaker 的長者本人，以候選專屬問題明確回答；
- `WITNESSED_VOICE`：長者本人說出同意，Staff／Family 只見證 Speaker 身份與回答確實發生。

`WITNESSED_VOICE` 的 witness 不是 consent actor，不能替長者說「好，記住」，也不能只按確認按鈕就
完成 Elder consent。只有未來另有明確法律代理權限模型、目的範圍與稽核證據時，才可另立決策允許代理。
MVP 不要求 voice biometric；但必須有受控 Session、Speaker verification state、candidate-specific
prompt、deterministic yes／no intent 與 ASR confidence gate。模糊、低信心或答非所問時維持
`PENDING_CONFIRMATION`。

### 6. HIGH 不建立 Memory，只留最小政策稽核

健康／疾病／用藥判斷、孤獨／憂鬱推估、家庭衝突、財務、未核實第三人敏感描述，以及無法安全分類的
內容，一律採限制性決策。第一階段：

- 不建立 `memory`／`memory_version`；
- 不保存敏感 proposal 原文、normalized content 或 embedding；
- 不進 Context、Graph、Summary 或 Family response；
- MAY 留下 append-only 的最小政策決策證據：`policy_decision=REJECTED_HIGH_RISK`、
  `memory_kind=SENSITIVE`、`policy_version`、source event／session reference、Speaker verification、
  consent version、bounded reason codes 與 `decided_at`。

這個最小 audit 可由既有安全稽核基礎設施或小型 `memory_policy_decision` record 承載，但不是 Candidate
aggregate。若同一來源包含合法 Care Event，Event 可按既有規則保留為 `NEEDS_REVIEW`；不得因此提升成
Memory。第一階段不提供人工把 HIGH promotion 為 Memory 的捷徑。

### 7. Care Event 與 Long-term Memory 分離

- Event 記錄「在某時發生／被陳述的事情」，保留 event time 與來源。
- Memory 記錄可供未來互動重用的穩定偏好、關係或習慣。
- Event review 與 Memory policy 是不同 Gate；Event VERIFIED 不自動建立 Memory。
- Memory 可直接引用 conversation／transcript source，不要求為了產生 Memory 而製造一筆不自然的
  Care Event；如確有 Event，則以 source reference 追溯。
- 「昨晚沒睡好」只能是時間性 Event，不能直接變成「長者睡眠不好」的永久 Memory。

### 8. 沿用 Memory aggregate，不先拆 Candidate table

目前沿用既有 `memory + memory_version` 表達候選與正式版本，不新增獨立 Candidate aggregate。目標狀態：

```text
MEDIUM: PENDING_CONFIRMATION → CONFIRMED → ACTIVE
                            → REJECTED
                            → DEFERRED
LOW:    policy-approved new version → ACTIVE
ACTIVE → INACTIVE → DELETED
```

沿用既有 `CONFIRMED` 可減少狀態遷移，但 confirmation 與 activation 必須在同一正式 transaction 完成；
`CONFIRMED` 不得成為可被外部檢索或長時間停留的半正式狀態。

沿用 `INACTIVE`，不新增同義的 `DEACTIVATED`。過期由 `valid_to` 加
`lifecycle_reason=EXPIRED` 表達，讀取時視為不可用，必要時由 deterministic job 轉 `INACTIVE`；不先新增
`EXPIRED` state。若未來出現大量批次審查、競合 proposal 或獨立候選保留策略，再另立 ADR 評估拆表。

### 9. Context Retrieval 是最後一道 deterministic Gate

每次組合 Agent Context 都 MUST 重新確認該 Memory：

- status 是 `ACTIVE` 且是 current version；
- `LONG_TERM_MEMORY` Consent 目前仍有效；
- Speaker ownership evidence 有效；
- 該風險層要求的 verification 已滿足；
- confirmation 綁定目前的 content digest、consent version 與可接受的 policy version；
- 未超過 `valid_to`，且未 INACTIVE／DELETED；
- tenant／elder 與本次授權 Context 完全一致；
- 未被更正、撤回、tombstone、replay 或 projection rebuild 復活。

不得只在寫入時檢查一次。舊資料、Graph、Search 或 cache 命中都必須通過同一正式 Core Gate 才能進
Agent Context。

### 10. 工程不變量

> No unverified speaker, unconsented memory, high-risk proposal, or stale confirmation may enter trusted memory or Agent context.

## 後果

正面後果：

- 低風險且由長者明確自述的偏好不再造成逐筆確認疲勞。
- MEDIUM 的每次確認都可證明長者確認了哪個精確版本。
- Staff-assisted 與多人環境不會把 initiator、witness、speaker 與 consent actor 混為一談。
- HIGH 不複製敏感原文，但仍能回答政策為何拒絕建立 Memory。
- 舊資料即使不符合新政策，也不能只因 status 為 ACTIVE 進入模型 Context。

成本與限制：

- Core 需要 deterministic Memory Policy、Speaker evidence、版本綁定確認與讀取時 Gate。
- Frontend／Voice flow 需區分 LOW 自動保存、MEDIUM 待確認與 HIGH 不顯示敏感候選。
- 既有 ACTIVE／PENDING 資料需要保守分類與 Expand → Migrate → Contract 演進。
- 未做 voice biometric 時，Speaker verification 依受控 Session 與見證證據，不宣稱生物辨識身份保證。

## 被拒絕的替代方案

1. **所有 Memory 一律逐筆確認**：安全但造成低風險確認疲勞，且沒有解決 Speaker 與版本綁定。
2. **完全相信 Agent risk**：模型輸出不是授權或安全事實，無法穩定重播與稽核。
3. **照服員按鈕可代長者同意**：混淆 witness 與 consent，對無帳號長者風險尤其高。
4. **HIGH 也建立 PENDING row 等人工審查**：會多保存一份敏感原文，且容易被未來流程誤啟用。
5. **現在新增 Candidate aggregate**：現有 `memory + memory_version` 足以承載第一階段狀態，現在拆分沒有
   足夠複雜度證據。

## 演進與驗證要求

本 ADR 只核准 Target Architecture，不授權直接改寫既有 migration 或宣稱已完成。實作必須採
Expand → Migrate → Contract，至少驗證：

- LOW all-of 條件任一失敗時零自動啟用；
- MEDIUM UI、voice、witness 路徑均綁定精確 version／digest；
- 修改 Candidate 後舊 confirmation 無效；
- witness 不能替長者同意；
- unknown／unverified Speaker 零個人 Memory side effect；
- HIGH 零 Memory row、零敏感 proposal 原文，僅留最小 audit；
- Consent revoke、expiry、INACTIVE、DELETED、cross-tenant／elder、stale version 均無法進 Context；
- replay、projection rebuild、cache 或 legacy ACTIVE row 不能繞過讀取時 Gate；
- Care Event VERIFIED 不會自動提升為 Memory。
