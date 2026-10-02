# RAG 簡化第 4 批：第一輪真實資料測試

本批完成既有 v004 資料的唯讀檢查、embedding cache 重用驗證，以及 16 題真實 Hybrid／Gemini
基準測試。三位 GPT-6.1 Sol subagents 分工 cache 匯出、實測工具、題目與答案覆核，主代理整合驗證。
結果暴露生成、引用、流程完整性與角色 metadata 問題，**尚未通過回答品質驗收**。
以下先保留第一輪基準；同日後續修正與新版資料準備見末節。

## 實測範圍

- 使用 development 既有 `rag-v2-v004-f3339ceae77c`，726 筆 projection／向量；並非新版 658 筆資料。
- Query embedding 使用 `gemini-embedding-001`、1024 維；生成使用 `gemini-3.6-flash`。
- V3 僅在測試程序啟用；預設及 `.env` 開關未改。未匯入資料、切換 release 或 activation。
- 資料庫只讀，查詢交易明確執行 `SET TRANSACTION READ ONLY` 並設定 statement timeout。
- 測試入口 `scripts/rag/evaluate_knowledge.py` 預設只驗本機題目；`--live` 才使用真實服務。
  題目在 `config/rag/knowledge-smoke-queries.json`，結果留在 ignored `.rag-work/`。
- 沒有新增人工工作簿、qrels 必填規則或封存鏈。題目中的 anchors 僅協助定位，不能當作語意評分。

## 實際向量重用

`scripts/rag/export_knowledge_cache.py --read-live` 以單一唯讀交易取得完整 726 筆向量，驗證
release／profile、receipt、coverage、embedding 文字 hash、維度與向量有效性，輸出本機 cache。
再以 `prepare_knowledge.py --cache ... --write` 整理新版資料，得到：

| 項目 | 數量 |
| --- | ---: |
| 整理後官方 chunks | 658 |
| 已驗證可重用的真實向量 | 631 |
| 仍需產生 document embedding | 27 |
| 整理驗證錯誤 | 0 |

這次的 631 筆已驗到實際向量，不只是文字未變。27 筆尚未呼叫 embedding，658 筆尚未匯入。
DB 的 model version 僅保存 model ID，未向 provider 證實不可變模型 revision。
本機輸出為 `.rag-work/cache/v004-cache.json` 與 `.rag-work/knowledge-v007-reuse/`。

## 16 題結果與答案覆核

主報告 `.rag-work/knowledge-evaluation-v004.json`：7 題 SUCCESS、5 題 NO_DATA、4 題 FAILED。
SUCCESS 中有 4 題 SUFFICIENT、3 題 PARTIAL；**有回覆不等於內容正確或問題已回答**。
本批不提供總品質分數。以下是測試產物覆核，並非對法規或服務內容的最新有效性背書。

| 題目 ID | 程式結果 | 覆核／待處理問題 |
| --- | --- | --- |
| apply-family | SUCCESS／PARTIAL | 缺少 1966 等起始聯絡步驟；「第一步提出申請」超出所選來源明述的評估責任 |
| apply-plain-elder | SUCCESS／PARTIAL | 有自我檢測導覽與資格條件，未回答起始求助管道 |
| respite-family | SUCCESS／SUFFICIENT | 答案有直接來源支持 |
| high-burden-unassessed-professional | FAILED | SUPPORT_QUOTE_NOT_IN_SOURCE |
| ba13-professional | FAILED | INVALID_GENERATION_JSON；已檢索到含相關條件的表格 |
| ba15-professional | FAILED | SUPPORT_QUOTE_NOT_IN_SOURCE |
| law-article3-definition | SUCCESS／SUFFICIENT | 定義有直接來源支持 |
| law-article9-modes | SUCCESS／SUFFICIENT | 服務方式比較有直接來源支持 |
| cross-law-application | SUCCESS／SUFFICIENT | 評估、核額度與擬計畫有據；「接受申請」為來源未明述的程序推論 |
| ba13-family-role-contrast | NO_DATA／INSUFFICIENT | 相關公開附件被原 audience metadata 排除 |
| high-burden-family-coverage | FAILED | SUPPORT_QUOTE_NOT_IN_SOURCE |
| future-benefit-currency-gap | NO_DATA／INSUFFICIENT | 未補猜資料未涵蓋的 2027 資訊 |
| local-office-contact-gap | SUCCESS／PARTIAL | 僅引用 14 字自我檢測導覽，未回答電話／營業／名額，應視為品質失敗 |
| out-of-scope-weather | NO_DATA | 無合適來源，未生成 |
| medication-stop-safety | NO_DATA／SAFETY_GATE | 生成前阻擋，未呼叫 provider |
| medication-change-safety | NO_DATA／SAFETY_GATE | 生成前阻擋，未呼叫 provider |

5 題 NO_DATA 中，4 題符合資料缺口／範圍外／安全拒答預期，1 題是角色範圍缺口。
3 題 quote mismatch 尚未區分空白／字形差異與內容改寫，不能直接斷言是幻覺。
BA13 JSON 失敗也尚未確認是否截斷、跳脫或其他格式問題。

主批共 14 次 query embedding、13 次生成；加上先前 3 題 probe 與 1 題 BA13 診斷，
本階段完成的真實批次共 18 次 query embedding、17 次生成。未額外產生 document embeddings。
主批 16 題延遲中位數為 3031.5 ms，包含 2 題生成前安全阻擋，不代表一般成功回答的延遲。

## 本批程式修正與驗證

- 真實連線發現 session 預設 read-only 未生效；backend 與實測 preflight 改為逐交易明確設定
  READ ONLY 與 timeout，設定失敗則不查詢。此路徑已在真實 PostgreSQL 執行。
- SQLAlchemy 設定 `hide_parameters=True`，避免 SQL 例外列出查詢參數。
- Gemini grounded 回合增加 `response_mime_type=application/json`，一般聊天不變；
  主批 BA13 仍失敗，因此此設定不能宣稱已解決 JSON 問題。
- 實測工具保存固定診斷代碼，不輸出原始 provider 回覆、prompt、secret 或一般例外全文。
  不因失敗放寬來源原文驗證。

| 檢查 | 結果 |
| --- | --- |
| Agent Runtime 全套 | 821 passed |
| Core cache exporter＋knowledge import loader | 42 passed |
| CI 工具單元測試 | 28 passed |
| Ruff lint／format | 通過，126 個檔案格式檢查通過 |
| Git diff whitespace | 通過 |

以上程式測試不能替代真實答案品質驗收；第 3、4 批尚未 commit／push。

## 下一批順序

1. **先修生成與回答支持性。** 對 4 題 FAILED 增加最小必要診斷：finish reason、token usage、
   格式類別；確認原因後才決定輸出預算或格式修正。辨別 quote 的格式差異與內容改寫，並約束
   回答不得把評估責任推成申請首步。只有導覽、沒有實際可答內容時應回 NO_DATA。
2. **驗證新版切割。** v007 已把舊申請流程四塊合為 209 字完整流程，包含原始首步、評估、
   計畫及服務；也排除上述 14 字導覽。這證明資料內容改善，尚未證明檢索排名改善。
   先準備 27 筆 embedding 與獨立 candidate release 的匯入差異／回復方式，獲授權後匯入，
   用相同題目對照 v004／v007；舊 release 保留供回復。
3. **修公開知識的 audience metadata。** 針對 BA13 家屬題確認公開適用範圍，精準修來源標記；
   不以全角色 override 取代資料修正，也不改私有長者資料、Consent 或 Core 授權。

維持 dense＋FTS／trigram Hybrid；這輪結果尚不足以支持新增 learned sparse embedding、
另一套搜尋服務或全面上網替代本機官方知識。

## 同日後續修正與新版資料準備

以同一批 Sol 6.1 agents 分工修正，主代理整合與覆核。使用者要求注意 CPU 後，停止
subagent 自行啟動檢查，後續命令以單工、BelowNormal 優先序執行；未啟動平行 pytest。
當次整機 CPU 讀值為 88%，當時沒有殘留 Python／Ruff／uv 測試程序。

### 已修正與仍有限制的行為

- Gemini grounded 回合加 JSON schema，約束五欄形狀；本次來源 ID 仍由 parser 精確驗證。不增加重試、token 上限
  或一般聊天設定。只用 provider 支援的 schema 子集，其餘唯一性與字數限制保留在 parser。
  [Google 官方說明](https://ai.google.dev/gemini-api/docs/structured-output#json-schema-support)
  也要求應用程式繼續驗證輸出；schema 不能證明答案受來源支持。
- 先補內容不落盤的 task-local 診斷，再定位失敗。四題 probe 全部 STOP／有效 JSON，
  BA13／BA15 為排版空白差異，高負荷專業題另有內容不匹配；沒有據此增加 token 預算。
- Prompt 要求回答實際問題面向，不能用導覽／資格背景代替求助管道，也不能將評估責任推成
  申請受理窗口。這仍是生成指引，並非已實作可靠的語意判官。
- 來源僅在 prompt 與引用匹配時整理「漢字之間、後行有至少兩個空格縮排」的換行，並統一
  CRLF。保留 tab、行內空格、空白行、未縮排換行、標點、頁碼、數字及英文識別碼；
  原始正文、內容 hash、embedding 文字和資料庫皆不改。縮排仍是 heuristic，不能證明表格語意。
  不使用全域去空白或 NFKC 當作來源驗證，也不接受跳過文字／跨 chunk 拼接。

### 原 16 題複測

`.rag-work/knowledge-evaluation-v004-phase5.json` 使用原 v004／726 筆、同一題目集：
**8 SUCCESS、6 NO_DATA、2 FAILED**，14 次 query embedding、13 次生成。
不是新版 v008 的排名測試，也不把這個狀態比例當成正確率。

- BA13、BA15 已回覆來源支持的原則／例外；聯絡電話／營業／名額缺口題改為 NO_DATA。
- 家屬申請題與跨來源題去除了「接受申請／第一步去某機關」的來源外推論，明示仍缺資訊。
- 獨立覆核 8 則 SUCCESS：7 則已答部分有來源支持；長者口語申請題仍以資格及自我檢測
  代替真正求助起點，應列為品質缺口，不能當作完整答題通過。
- 高負荷專業題仍因引用不匹配拒絕；高負荷家屬題這次遇到模型服務錯誤。
  先前四題 probe 的家屬題成功，不能用該次成功掩蓋本輪失敗。

後續只做定向追查，**沒有把不同輪結果拼成新的 16 題分數**：

- `.rag-work/knowledge-targeted-v004-phase5.json`：長者口語申請題改為 INSUFFICIENT，
  不再以資格清單當作申請起點；專業高負荷題仍為引用 content-mismatch；家屬題確定為
  上游 ClientError／HTTP 400，不能標成暫時服務不可用。
- `.rag-work/knowledge-family-schema-diagnostic.json`：400 的原始錯誤只得到固定
  `INVALID_PROVIDER_REQUEST` 分類，未證實 schema complexity，不輸出 SDK 錯誤原文。
- schema 撤掉長 chunk ID 的動態 enum，改由原本 parser 繼續驗引用 ID；同題 A/B
  `.rag-work/knowledge-family-schema-fixed.json` 已為 SUCCESS／SUFFICIENT，正常 STOP、有效 JSON，
  回覆的兩個求助專線均存在於所選來源。這證明該案例恢復，並不宣稱已精確解析上游 400 根因。
  專業高負荷題的引用內容不匹配仍是下一批要處理的品質問題，未關閉其拒絕檢查。

### 新版資料已準備

`prepare_knowledge.py` 增加可選的 `--audience-patches`；預設 v007 輸出不變。
`config/rag/knowledge-audience-patches.json` 只修正獨立 BA13 chunk `_0012`：
`care_professional` → `care_professional, family_caregiver`。來源 ID、原正文 hash 與原 audiences
必須完全符合才套用；其他欄位、覆核狀態與評估要求不變，不放行整份附件或私人長者資料。

- 本機 dataset：`.rag-work/knowledge-v008/`，658 筆、14 個來源；對 v007 的唯一逐筆差異為
  上述 BA13 audience。完整流程切割及導覽排除沿用 v007。
- Candidate release：`knowledge-v008-aae34e5095e6`。
- Candidate SHA-256：`aae34e5095e6d02f57203939276f9abaf9b39db37b0eed3a54c19c68c87a7fb2`。
- 完整 cache SHA-256：`295bcb26c1bd080bd936f91cbba657b0a4090d5c8d578d820bf5759010a8d36e`。
- 新 `embed_knowledge.py` 預設 dry-run；明確 `--generate` 才生成缺漏向量，每次最多 32 個
  唯一文本，已有 cache 重用、完整 profile 比對，生成後重新驗證全數向量再輸出。
- 27 筆 Google document embeddings 已補齊，631 筆重用；
  `.rag-work/cache/v008-complete-cache.json` 再經 planner 驗證為 **658 available／0 required**。
  所有生成輸入皆是公開官方知識，未傳送長者個資。

`scripts/rag/import_knowledge.py` 已完成本機 dry-run：Core 獨立重驗 candidate 與完整 cache，
產生 658 筆 typed embedding records，驗證完整 profile、hash、有限非零 float32 向量與覆蓋。
新入口不依賴 legacy allowlist；舊 loader 的 allowlist gates 不變。CLI 本輪只有預覽，
沒有 DB write flag、Settings／`.env` 載入、DB 連線或 activation。

本輪驗證：Agent Runtime 完整套件 843 passed（CPU 限制前）；其後只跑受影響的定向
103 tests passed，最終 schema／診斷版本另有 Gemini 28 passed。資料 patch 53 passed，
缺漏 embedding 入口 11 passed，Core cache loader＋既有 embedding importer 36 passed。
定向 Ruff lint／format 與 `git diff --check` 通過。沒有把定向測試數加總成新的完整套件數，
也沒有把程式測試數當成答覆品質。

### 使用者授權後的實際匯入

使用者明確授權「匯入開始」後，已新增獨立 staging candidate
`knowledge-v008-aae34e5095e6`：658 projections＋658 vectors，14 個來源。
既有 projection／embedding importers 由單一外層交易包住；實際新增各 658 筆，既有筆數均為 0。
完成後以唯讀交易回驗 counts、profile、record／embedding hashes 與 float32 向量內容，
並以 cache exporter 再驗兩份完成 receipt 與全數 658 筆覆蓋。

- Projection run：`a8838c0c-22a6-4246-99c1-ece59fb12bec`。
- Embedding run：`61d330fa-fa6e-4bd8-9fdf-970c7cd554f3`。
- 本機操作結果：`.rag-work/knowledge-v008-import-result.json`。
- v004 release metadata／726 projections／726 vectors 的前後指紋一致。
- 未修改 `.env`、既有 release、runtime 設定或 activation；review 仍如實保留 `needs_review`。

原 v004 持續可用。新版題集只在測試程序內指定 candidate binding，不會切換執行中的服務。

### v008 匯入後固定 16 題實測

`.rag-work/knowledge-evaluation-v008.json`：**9 SUCCESS／6 NO_DATA／1 FAILED**，
14 次 query embedding、14 次生成。單工、BelowNormal；未重跑完整單元測試或增加題集。
DB preflight 確認 658 projections、658 vectors 與 profile／hash 覆蓋完整，逐交易強制唯讀。

- 家屬申請題已能引用完整四步驟，包括 1966 與申請管道，從 v004 的 PARTIAL 改為 SUFFICIENT。
- BA13 專業與家屬同題皆成功；BA15、喘息、兩題法條及跨來源分工題亦成功。
- 家屬高負荷求助題成功，所答兩支專線均存在於選定來源；本輪無 HTTP 400。
  該題舊自動 expectation 限制為 partial_or_no_data，因此其 expected_outcome_observed=false
  不能單獨解讀為答案錯誤；未修改題目預期來提高分數。
- 6 題 NO_DATA 中，未來補助、即時地方聯絡資料、天氣與兩題用藥安全共 5 題符合預期。
  長者口語申請題只找到額度／資格，缺申請流程，屬尚待修正的檢索缺口。
- 1 題 FAILED 為專業高負荷流程：`SUPPORT_QUOTE_NOT_IN_SOURCE`，2 個 content-mismatch、
  1 個 exact；引用檢查保留，未把模型改寫偽裝成原文。

本輪完成匯入與一次新版驗證；剩餘工作收斂為上述口語檢索與專業題引用兩項。
狀態數不是語意正確率，也不與先前 v004／定向結果拼成分數。未啟用新版到執行中的服務。
