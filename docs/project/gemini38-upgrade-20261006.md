# Gemini 3.8 Flash generation 升級

2026-10-06，使用者授權將專案 3.6 generation model 升級。

Google [模型文件](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)列出穩定版
`gemini-3.8-flash`；支援 LOW／MEDIUM／HIGH thinking，MINIMAL 會回錯誤。
[API 停用表](https://ai.google.dev/gemini-api/docs/deprecations)在本次查詢時尚未公布 3.6
停用日期，因此不將其他產品的停用訊息當成 Gemini API 的已確認日期。

## 變更

Native Gemini adapter 對確切的 3.8 model ID 設 LOW thinking、include_thoughts=false，
沿用模型預設 temperature；3.6 仍用原 MINIMAL，其他明確選用的模型保留設定的 temperature。
不使用名稱前綴自動推測模型能力。原有一般 512-token budget、grounded 2048-token floor、
4,000 字元回覆限制、JSON schema、來源引用與安全 gate 維持。

本機 ignored `.env` 的 GEMINI_MODEL_ID 與 OPENAI_COMPATIBLE_MODEL_ID 兩個值改為
`gemini-3.8-flash`。Provider 保持 gemini，真實驗收使用既有 Vertex AI Express 憑證。
已核對 model 欄位及 service-local 覆蓋，再只更新這兩個值；沒有將 `.env` 納入版控。
8001 Agent 已驗明程序擁有者後重啟。本次 generation 切換不重算或混用 embeddings；
`gemini-embedding-001`、v008 release 與既有向量保留。

## 驗證

- BelowNormal、單工執行 Gemini provider／grounded answer／evidence service：157 passed。
- 兩個修改 Python 檔 Ruff lint／format check 通過。
- 28 項 CI 影響與 workflow 規則測試通過。
- 真實 Vertex 合成陪伴呼叫：3.8、STOP、49 字元，512 budget 內取得回覆。
- 日常 BFF → Core → Agent：家屬申請 ANSWER／2 來源，居服申請 PARTIAL／1 來源；
  法條各 ANSWER／1 官方來源。兩角色未來額度各 NO_DATA、停藥各 BLOCKED；
  登入、登出均成功，共 12 項 smoke 檢查通過。

這些驗證是模型相容及開發環境回歸，不代表獨立答案準確率評估。尚未驗證相容 API
provider 的真實 transport，也不宣稱本次已完成 production 或 55 筆來源版面修復。

程式提交由新分支、最新 main 基底管理；秘密值與合成問句／模型原文不放入文件或 PR。
