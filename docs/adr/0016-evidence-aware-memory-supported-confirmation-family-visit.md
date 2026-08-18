# ADR 0016：Evidence-aware Memory、支持式確認與 Family Co-Companion 邊界

- 狀態：Proposed Target Architecture；須經 Product Owner、Domain、Safety、Data Governance 與臺灣法務／照護倫理審查後才可標記 Accepted
- 日期：2026-08-18
- Owner：Project Owner／Domain／Safety／Data Governance
- 延伸：[ADR 0014](0014-risk-tiered-memory-speaker-verification.md) 的 LOW／MEDIUM／HIGH、Speaker Gate、Elder confirmation 與 retrieval-time Gate
- 不取代：ADR 0014 中「Staff／Family witness 不得取代 Elder consent」、「HIGH 不建立 Memory」及「Agent proposal-only、Core authority」
- 設計輸入：[Evidence-aware Memory 與 Family Co-Companion brief](../codex_brief_evidence_aware_memory_family_co_companion.md)

## 背景

Kinsun 已用 ADR 0014 決定：LOW 通過 Core all-of policy 後可直接 `ACTIVE`，MEDIUM 必須由長者本人
對固定版本確認，HIGH 不建立 Memory。新的設計 brief 進一步提出三個互相關聯、但不能混成單一信任
分數的問題：

1. 長者、家屬或照護者說過的內容，不等於客觀世界已驗證的事實；
2. 認知障礙、失智、譫妄或狀況波動，不代表長者在所有時間、所有事項都沒有決策能力；
3. 家庭共伴會客需要短效、限範圍的共同互動能力，不能把 Staff App Session 或家屬報表權限直接交給
   共用平板。

目前 repository 已有可延伸的 `CareEvent`、immutable `CareEventVersion`、append-only `ReviewDecision`、
`Memory + MemoryVersion`、Consent、CareRelationship、FamilyRelationship、Core App Session、Voice Ticket、
Transactional Outbox 與 synthetic graph projection。尚未有通用 Claim aggregate、ConflictGroup、
DecisionSupportProfile、VisitSession 或一般 CareTask 實作。因此本 ADR 採最小延伸，不把 brief 中的候選
類別或 route 名稱誤寫成現況。

健康、疾病與病歷資料亦不是一般個人化資料。臺灣《個人資料保護法》第 6 條對病歷、醫療與健康檢查
資料的蒐集、處理與利用另設限制；監護／輔助及代理權也不能只由疾病名稱或家屬關係推定。產品在實作
前仍須完成臺灣法務與照護倫理審查。

## 決策

### 1. Confirmed Memory、Reported Statement 與 Verified Fact 永久分離

Core MUST 分開表達下列語意：

- `ReportedStatement`：可證明某個 Speaker 在特定時間說過某段內容；
- `CareEvent`：帶時間、來源、驗證狀態與可行動性的生活或照護事件；
- `MemoryCandidate`：可能適合未來個人化，但尚未滿足必要政策的固定版本；
- `ConfirmedMemory`：已依當時適用政策完成必要確認、可在有限用途下進 Context；
- `VerifiedFact`：另有足以支持客觀或可行動主張的外部、Staff 或 System evidence。

因此：

```text
ELDER_CONFIRMED != VERIFIED_FACT
FAMILY_CONFIRMED != ELDER_CONFIRMED
KNOWN_SPEAKER != TRUE_CONTENT
```

「我今天已經吃藥」即使由 Elder 本人確認，也只能先是 `SELF_REPORTED` CareEvent；在外部驗證前不得成為
已服藥事實、用藥結論或會驅動高風險提醒的 Memory。

### 2. Memory admission 是多條件 Gate，不是一次按鈕

Memory 只有在下列條件同時成立時才可 `ACTIVE`：

```text
current consent or valid authority
AND eligible memory kind
AND sufficient speaker ownership evidence
AND risk-specific confirmation or auto-policy
AND required verification satisfied
AND no unresolved blocking conflict
AND current version / digest / policy binding
AND tenant / elder / visibility scope match
AND valid lifecycle and retention window
```

`confirmation` 是 Gate 中的一項證據，不是客觀真實性的替代品。LOW／MEDIUM／HIGH 的最低限制仍由
ADR 0014 決定；本 ADR 的 profile MAY 收緊特定長者、資料類別或時間範圍的政策，但 MUST NOT 放寬
ADR 0014 的最低安全門檻。

### 3. 不建立全域失智、混亂或可信度分數

Core、Agent 與 UI SHALL NOT 建立或推導：

```text
elder_is_confused
elder_global_capacity
elder_trust_score
dementia_means_unreliable
```

疾病紀錄本身不得直接讓所有 Elder confirmation 失效，也不得自動授權 Family／Staff 代答。需要調整時，
必須針對「特定資料類別、特定決定、特定有效期間」採支持式確認或保守政策。

### 4. 採三層資料與政策分離

```text
RestrictedCareRecord
        -> minimal policy reference
DecisionSupportProfile
        -> deterministic confirmation requirements
MemoryPolicyGate
```

#### 4.1 RestrictedCareRecord

實際診斷、病歷、健康狀況與臨床紀錄：

- 不放入一般 `Memory`、Memory embedding 或個人化 Graph edge；
- 不預設進 Agent prompt、Family response、Family Visit context、一般 Search 或 Summary；
- 只允許具明確 sensitive scope、有效 assignment／relationship 與 purpose 的授權角色讀取；
- audit 只記 resource reference、actor、purpose、policy decision 與結果，不複製診斷原文；
- retention、legal hold、更正與刪除遵循適用法律及機構政策，不與一般 Memory retention 混用。

不得為方便 Memory policy 而在多個表、Log、Graph 或 prompt 中複製完整診斷。若 Memory Gate 需要知道
確認模式，只讀取最小化的 profile 與不透明 `basis_reference`。

#### 4.2 DecisionSupportProfile

`DecisionSupportProfile` 不是診斷紀錄，也不是自由調整「可信度」的 UI。最小語意為：

```text
profile_id
elder_id / tenant_id
decision_scope              # e.g. MEMORY_CONFIRMATION
data_class                  # preference, life_story, relationship, schedule...
mode                        # STANDARD | SUPPORTED | REPRESENTATIVE_REQUIRED
allowed_memory_risks
basis_reference             # points to restricted authoritative record
effective_from / expires_at
reviewed_by_actor_id
policy_version / profile_version
created_at / supersedes_profile_id
```

規則：

- 只能由明確授權且具資格的人工角色，依正式紀錄建立或更新；LLM 不得寫入或自行推測；
- 必須有 scope、版本、期限、來源與 audit，過期或資料不足時 fail closed；
- profile 只能收緊、分流或要求支持，不能把 HIGH 轉成 Memory；
- `SUPPORTED` 表示仍由 Elder 作成該次決定，Staff／Family 只能協助理解、溝通與見證；
- `REPRESENTATIVE_REQUIRED` 不會把 representative 的回答改標成 `ELDER_CONFIRMED`，而是停止建立新的
  Elder-owned ACTIVE Memory，必要內容保持 `REPRESENTATIVE_REPORTED`／`FamilyContribution` 或正式照護
  紀錄，等待獨立授權與用途政策。

#### 4.3 MemoryPolicyGate

| Profile | LOW 主觀偏好 | MEDIUM 穩定記憶 | OBJECTIVE／HIGH |
|---|---|---|---|
| `STANDARD` | ADR 0014 all-of 通過可 auto-active | Elder version-bound confirmation | 不以 self-confirmation 變成 fact；HIGH 零 Memory row |
| `SUPPORTED` | 可由 profile 對特定 kind 縮短 `valid_to`、要求重新詢問或升為 MEDIUM | 簡短單一問題、可理解表達、`not sure/later`、必要 witness；模糊或矛盾維持 Pending | 僅 self-reported Event／正式人工流程 |
| `REPRESENTATIVE_REQUIRED` | 不從新對話建立 Elder-owned ACTIVE Memory | 不建立 `ELDER_CONFIRMED` | Contribution／正式照護紀錄；HIGH 仍零 Memory row |

支持式確認 SHALL 提供「記住／不要記／不確定／稍後」、一次一項、可重述、可使用圖片或語音，並記錄
實際 Elder response。系統不得反覆詢問直到得到「是」，也不得用照護者按鈕替代 Elder response。

### 5. Consent authority、content provenance 與 witness 分離

Core MUST 分開保存：

- 誰有權同意系統處理該 purpose 的資料；
- 內容是 Elder、Family、Staff、Device 或外部紀錄中的哪一方提供；
- 誰見證 Speaker 身分與當時回答；
- 誰驗證客觀事件；
- 誰具有經核驗且仍有效的法律代理權、其 purpose 與範圍。

疾病診斷或 `FAMILY_MEMBER` role 不等於法律代理權。未來若支援代理同意，必須有獨立、可撤銷且可到期的
`LegalAuthority`／authorization reference，至少包含 authority type、representative、covered purposes、
source document reference、verification、effective window 與 audit。這不授權 representative 把自己的
陳述冒充 Elder statement。

### 6. 先延伸 CareEvent，不先建立通用 Claim aggregate

第一階段沿用 `CareEvent + CareEventVersion + ReviewDecision` 承載 Reported Statement 與驗證歷程，補上
或關聯：

- speaker role／id／verification method；
- source type／source reference；
- verification status／method／actor／time；
- visibility scope、actionability、policy version 與 trace；
- evidence reference 與 conflict membership。

`Memory` 可引用 conversation／turn／session 或真正存在的 CareEvent；LOW 偏好不得為了配合舊 pipeline
而製造假的 CareEvent。只有在一個 Event 無法合理承載多個異質 claim、或 conflict resolution 需要 claim
級生命週期時，才另立 ADR 評估 Claim aggregate。

### 7. Confirmation 使用 append-only record；Conflict 使用獨立 aggregate

`memory_confirmation` SHOULD 是 append-only record，綁定：

- memory／version／content digest；
- consent／policy／profile version；
- method、Elder response intent、speaker evidence 與 witness evidence；
- actor、session、trace、correlation、idempotency 與 timestamp。

Aggregate 上的 `confirmed_by/at/method` 可暫時保留為 current projection，但不得成為唯一證據。

衝突第一版採 `ConflictGroup + ConflictMember + ConflictResolution`，保留所有來源與決策；不先把
`DISPUTED` 加入 Memory 核心 state，也不把 `CONFLICTING` 加入 CareEvent 核心 state。未解衝突由 relation、
retrieval exclusion reason、visibility 與 actionability Gate 表達。只有後續證明關聯模型不足，才另立 ADR
擴充 aggregate state machine。

第一階段不為衝突建立通用 CareTask framework；先用專用 review queue／review item，避免為單一流程新增
尚無其他消費者的工作管理領域。

### 8. FamilyContribution 永遠保留第三方來源

Family／Staff 已驗證身分，只能證明「是這個人提供內容」，不能證明內容為真，也不能證明是 Elder 的
偏好。`FamilyContribution`：

- 預設是 Candidate／evidence，不是 ACTIVE Memory；
- 不投影為 Elder-owned active memory edge；
- 經 Elder 依適用 policy 完成標的明確的確認後，才 MAY 產生新的 Elder-confirmed Memory version；
- Elder 無法完成本次確認時，維持第三方 contribution、conflict evidence 或正式照護紀錄，不由 caregiver
  代為 activation；
- 客觀、可行動或 HIGH 內容仍需相應外部驗證，Elder confirmation 也不能跳過。

### 9. Family Co-Companion 使用獨立 VisitSession capability

Family Visit 不重用 Staff 的 Core App Session，也不把一般 Family App Session 交給共用平板。目標
`VisitSession` 必須：

- 限 tenant、elder、visitor、relationship、permission scope 與有效時間；
- 使用獨立 opaque、短效、可撤銷、不可恢復的 credential；
- 每次 request 由 Core 重載 session、consent、relationship、scope、status 與 expiry；
- 明確 `CREATED -> ACTIVE -> ENDED`，並支援 `CANCELLED`／`EXPIRED`；
- 結束、到期、撤回或換人後清除 tablet context、cache 與本地敏感狀態；
- 只讀 `FAMILY_SHAREABLE` read model，不回傳 raw transcript、restricted health record、未覆核 signal、
  conflict details 或 risk score；
- 在 Elder 可直接互動時預設促進 Elder 與 Family 對話，不替 Elder 回答。

Family Visit 與現有只涵蓋正式家庭報表的 `FAMILY_SHARING` 是不同資料用途。Target Architecture 新增
獨立 `FAMILY_VISIT` consent purpose；若法務／產品最終選擇 scope-based extension，必須以新 ADR 明確
取代此決策、重新告知並重新取得有效 consent，不得靜默擴張既有 grant。

### 10. PostgreSQL／Domain Core 是權威；Graph 只做可重建投影

正式 Consent、authority、profile、verification、confirmation、conflict、VisitSession 與 lifecycle 均由
authoritative relational Core 保存。Graph／Search 只能透過 Transactional Outbox、idempotent consumer、
retry／DLQ 與 replay 建立投影。

Graph MAY 收錄通過 policy 的 ACTIVE Memory、已驗證且允許投影的 Event、正式關係與 shareable edge；
不得收錄未確認 FamilyContribution、restricted health detail、HIGH proposal、unknown／multiple speaker
personal memory 或 blocking conflict。所有 Context read 仍回查 Core current state；Graph lag、SYNCED 狀態或
舊 edge 不能授權資料使用。

## 實作階段

### Phase 0：ADR 與現況基線

- 本 ADR 與 brief 建立決策權威／輸入文件關係；
- 明確記錄 current-state gap，不把 Target route、table 或 enum 宣稱已存在；
- ADR 0014 仍是 LOW／MEDIUM／HIGH 與 Elder confirmation 的最低權威。

### Phase 1：Evidence-aware Memory Core

- 完成 ADR 0014 的 Speaker evidence、Core-owned risk policy、LOW auto-active、MEDIUM version/digest-bound
  confirmation、HIGH minimal audit 與 retrieval-time final Gate；
- 補 CareEvent source／verification metadata 與 append-only `memory_confirmation`；
- 導入最小 DecisionSupportProfile 讀取 Gate；RestrictedCareRecord 只提供不透明 basis reference；
- legacy ACTIVE／PENDING 資料採 Expand -> Migrate -> Contract，未知來源不得自動升級；
- feature flags：`evidence_aware_memory`、`auto_low_risk_memory`。

### Phase 2：Caregiver Review 與 Conflict

- 新增 ConflictGroup／Member／Resolution、專用 review queue 與候選／衝突 UI；
- 支援修正、拒絕、停用、刪除、projection removal 與 replay；
- 不提供 caregiver-as-Elder confirmation，也不新增 HIGH promotion 捷徑。

### Phase 3：Family Co-Companion

- `FAMILY_VISIT` Consent、VisitSession domain、短效 capability 與獨立 BFF／Core 驗證路徑；
- FAMILY_SHAREABLE read model、FamilyContribution、tablet timer／end／cleanup 與 post-visit review；
- feature flag：`family_visit_mode`。

### Phase 4：Enhancement

- 共同回憶時間軸、照片／歌曲／地方故事、進階 Graph query、跨日 follow-up 與 personalization eval；
- 不得在前述安全 Gate 未完成前提前開啟。

## Migration 與 rollout

所有 schema／contract 演進採 Expand -> Migrate -> Contract：

1. 新 reference／status metadata 先 nullable，new writer 雙讀相容但不得無保護雙寫；
2. legacy Memory 無法證明 speaker、consent、risk、verification 或 version binding 時標記
   `LEGACY_NEEDS_REVIEW`／以 retrieval Gate 排除，不偽造 confirmation；
3. 新 projection consumer 上線前保留舊 reader，完成 replay、removal 與 stale-event 測試；
4. rollback 不得使新 restricted／conflicting／revoked 資料被舊 reader 誤視為 ACTIVE；
5. feature flag 關閉時仍須保留 deny-by-default、consent revocation 與 tombstone 行為。

## 驗證要求

至少涵蓋：

- 失智或認知障礙診斷存在，但無有效 profile：不得推定無決策能力，也不得讓 Family 代答；
- `SUPPORTED` profile 的 LOW／MEDIUM flow，含不確定、稍後、答非所問與矛盾回答；
- expired／cross-elder／unauthorized profile 或 authority reference fail closed；
- Elder confirmation 不把用藥、行程、財務或法律陳述變成 Verified Fact；
- FamilyContribution 未經合格 Elder confirmation 不進 ACTIVE Memory／Graph／Context；
- guardian／representative 可在核驗範圍內提供 consent authority，但內容 provenance 不被改成 Elder；
- restricted health record 不進一般 Memory、Agent prompt、Family response、Graph、Search 或 raw audit log；
- conflict 保留所有 evidence，未解時阻擋 actionability 與 retrieval，不無痕覆寫；
- VisitSession cross-elder、expired、ended、revoked、replay、IDOR 與 tablet context cleanup；
- Consent revoke、relationship expiry、Memory delete／inactive 與 projection replay 都不能復活存取。

## 後果

正面：

- 尊重 Elder 仍保有的決策能力，又不把一次確認誤當客觀事實；
- 疾病與健康資料不會因個人化需求擴散到 Memory、Graph、Family 或 prompt；
- Family／Staff 可提供 evidence 與支持，但不會取得隱含的 Elder confirmation authority；
- VisitSession 有獨立的最小權限與可撤銷生命週期；
- 現有 CareEvent、Memory、Outbox 與 authorization foundation 可逐步延伸。

成本：

- 需要新的 append-only confirmation、profile、conflict 與 visit persistence；
- Consent contract、OpenAPI、Core policy、Frontend、Graph consumer、migration 與 failure-path tests 都會擴充；
- profile 設定資格、legal authority verification、retention 與 Family Visit 告知文字需要跨專業審查；
- 本 ADR 涵蓋三個實作 phase，不能視為單一 sprint 或 ADR 0014 Gate 的替代品。

## 被拒絕的替代方案

1. **診斷失智後所有 Elder confirmation 一律無效**：把疾病當成全域能力判決，過度限制自主且不符合
   decision-specific、time-specific 的產品安全原則。
2. **家屬或照護者可直接代按確認**：混淆 witness、consent authority、content provenance 與客觀驗證。
3. **把完整疾病資料送入 Agent 判斷是否相信長者**：造成敏感資料擴散，且讓模型作不應由模型作成的
   能力／醫療判斷。
4. **每種陳述先建立 Claim aggregate**：現有 CareEvent version／review foundation 尚可承載第一階段；
   現在拆分缺少足夠複雜度證據。
5. **用 `DISPUTED`／`CONFLICTING` 擴張所有核心狀態機**：會同步擴大 API、projection、migration 與舊
   reader 風險；第一階段 relation aggregate 足夠。
6. **VisitSession 重用 Staff App Session 或 FAMILY_SHARING grant**：會讓共用裝置取得過廣權限，且把
   報表分享同意靜默擴張為現場互動存取。

## 仍待決策

- 哪些專業角色可建立／覆核 DecisionSupportProfile，及其機構責任與訓練要求；
- RestrictedCareRecord 的法定蒐集依據、保存期限、刪除例外與 legal hold；
- `FAMILY_VISIT` 的正式告知文字、代理同意範圍與現場再次確認方式；
- verified legal authority 的文件核驗、撤銷與到期流程；
- conflict review 是否在多個 domain 出現到足以升級為通用 CareTask；
- production Graph backend 與 projection SLA；本 ADR 不宣稱 Neptune 已部署。

## 相關文件與外部依據

- [ADR 0014](0014-risk-tiered-memory-speaker-verification.md)
- [Spec 18](../spec/18智慧長照%20AI%20陪伴系統－風險分級長期記憶、Speaker%20驗證與版本綁定確認%20v0.1.md)
- [Evidence-aware Memory 與 Family Co-Companion brief](../codex_brief_evidence_aware_memory_family_co_companion.md)
- [個人資料保護法第 6 條－全國法規資料庫](https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=I0050021&flno=6)
- [監護宣告及輔助宣告－司法院](https://www.judicial.gov.tw/tw/cp-107-58173-364a9-1.html)
