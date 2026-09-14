# 上次服務紀錄：真實登入驗收

2026-09-14，產品程式基準為已合併 PR #44 的 `4556e57`。
[main CI 34813366993](https://github.com/71bk/kinsun.ai-product/actions/runs/34813366993) 全部成功。
使用重新建立的 production frontend、Core 與 Supabase development database；revision
`e3a5c7d9f102`。沒有 Docker、schema rebuild、fake auth、API response mock 或 session cookie 注入。

## 範圍與資料來源

對應 US-C01／US-C02／WF-05／NFR-H01；本次本人有效 IN_PROGRESS 派案與獨立
`service_record:history:read` 是入口，來源仍須通過同 tenant／elder／unit、正式版本與時窗 gate。

Campaign `previous-record-real-auth-20260914` 建立兩個全新的 synthetic HOME_CARE_WORKER，
各用真實 KINSUN identity、Argon2id credential 與表單登入取得 HttpOnly App Session。
四筆 membership 最長四小時，不延長既有帳號或授權。兩個合成 tenant／unit／elder、六筆派案
只服務本次測試；第二個 tenant 是負向 canary，reader 沒有該 tenant membership。

歷史原文是明確標記 synthetic 的人工 fixture，來源作者是 writer；不是聲稱昨天經 UI 寫入。
新紀錄則由 reader 經 Browser → BFF → Core → DB 實際提交，兩種證據分開記錄。
沒有 Agent、醫療建議、真實個資、通知發送或 production activation。

| 角色／資源 | ID |
| --- | --- |
| writer | `ab167e46-dc84-5170-8309-16eeb383974d` |
| reader | `a3c9dbf3-6b38-5831-9494-7b828423395b` |
| 歷史來源派案 | `25c2bd3c-a2b9-5d57-bbec-94162d82433e` |
| 歷史來源紀錄 | `596398e1-c1be-57bb-a612-194f309c9e3a` |
| reader 本次完成派案 | `e9be3cef-afa6-5849-9e8c-d0f1de2765b0` |
| reader UI 新紀錄 | `6a7b2df8-3346-4de3-9b68-ee5a2276b430` |

## 實際結果

| 驗證 | 結果 |
| --- | --- |
| 兩個真實帳號登入 | `/me` 各自回對應 Actor ID；沒有沿用 demo 密碼或注入 token |
| writer 本次派案讀舊紀錄 | 200；直接以已完成來源派案 ID 讀取則 404 |
| reader 跨 worker 交接 | 200、no-store；source record ID／原文／version 1／Asia/Taipei 均一致，回應不含 worker ID |
| 缺少 history scope | 404；其他有 scope 的派案不能補足，UI 不顯示入口 |
| 別人的派案／跨 tenant／舊派案 | 均 404，公開 error code／message 與不存在資源相同 |
| UI 展開／收起 | 真實原文可見；收起後 DOM 不留原文 |
| UI 提交並完成 | 表單填 synthetic note、勾選完成、二次確認；實際 POST 回 201 |
| DB 讀回 | 新紀錄 v1、作者 reader；本次派案 COMPLETED v3；新增兩筆對應 outbox |
| 完成後 reader 再讀本次 history | 404；重載後卡片為 Completed v3，沒有紀錄讀寫入口 |
| 最後撤權後舊畫面 | writer 展開原文後撤銷 campaign；下一輪重查 401，原文及全部 article 清除，顯示 Content is unavailable |

新增 outbox 僅有 `care.service_record.completed.v1` 與 `care.assignment.completed.v1`，
aggregate 分別指向上述新紀錄與本次派案。歷史來源 fingerprint 始終為
`2a0c408d4bb2df76b733faf84348fa5a319315cf66a0da31b5290b63bd90ad81`。
成功提交後至全部撤權後，兩筆紀錄＋兩筆 outbox 全欄位 digest 均為
`8a173169163d9bdcf26437da799e5ed6440a35723cc09b6285f5ffe717196422`。
這是 campaign 的有界核對；登入會修改 auth/session 狀態，不宣稱全 DB 零寫入。

## 畫面與腳本

本機 Playwright CLI 讀取 git-ignored 私密 fixture，密碼不寫入命令列或證據輸出。
MCP runtime 不提供 require／dynamic import，因此沒有用它讀取憑證；截圖另以 image viewer 檢查。
英文 desktop 1440 與 mobile 390 的 innerWidth／clientWidth／scrollWidth 完全一致，無水平溢位。
原文、日期／時區／版本及觸控入口已檢視；前一階段 14 組雙語 synthetic QA 仍是其他尺寸證據。

- `.qa/previous-real-auth.cjs`：`read`、`write-expiry` 與接續驗證模式。
- `.qa/previous-real-read-evidence.json`：兩個 principal、負向 gate、跨 worker 讀取與三張截圖。
- `.qa/previous-real-writer-expiry-evidence.json`：最後 writer 撤權的 401／DOM 清除與截圖。
- `.qa/previous-real-writer.png`、`previous-real-reader-desktop.png`、`previous-real-reader-mobile.png`。
- `.qa/previous-real-confirmation.png`：提交前人工二次確認；full-page 固定 overlay 的位置僅作流程證據，不作 viewport 幾何判定。
- `.qa/previous-real-before-expiry.png`、`previous-real-after-expiry.png`：最後 writer 撤權前後。

未驗真機、screen reader 全流程、Lighthouse、外部部署或 production 資料量。

## 過程中的修正與證據限制

1. 第一版 fixture 只有據點 membership；正確密碼仍因缺少 tenant-level membership 無法發 session。
   僅補兩個新帳號、沿用原期限；產品登入 gate 未改。fixture 已修正，並補離線期限測試。
2. 負向回應的 `correlation_id` 本來就各異；QA 改比對公開 code／message，不把 trace ID 當資源差異。
3. UI POST 依契約回 201，腳本誤預期 200 而中止；讀回確認成功後不重送，接續驗證完成派案的拒絕。
   沒有取得該次即時成功 toast 截圖；成功依據為實際 HTTP、DB／outbox 與重載畫面。
4. 只讓 reader 的據點 membership 到期時，tenant-level membership 仍能授權，200 符合現行 gate。
   reader 的兩層權限其後均到期，原等待腳本已 timeout；未續期 reader，改以仍有效的 writer
   執行最終撤銷與舊畫面清除，結果通過。這不是 reader 單一 membership 到期成功的證據。
5. 一次只讀 inspection 遇到 ConnectionDoesNotExistError，後續重新連線成功；沒有印出 DSN。
6. 環境診斷曾發生遮罩不完整；需處理的既有設定輪替見
   [development auth follow-up](development-auth-rotation-followup-20260914.md)。尚未輪替，不視為安全待辦結案。

## 撤銷與驗證

`scripts/qa/previous_record_fixture.py` 預設 read-only inspect；任何 write command 都需要顯式 opt-in。
prepare 拒絕既有 campaign，add-login-memberships 不可覆寫或延長；retire 僅處理固定 ID、驗證
ownership 後縮短期限，保留 immutable notes／assignments／outbox 供稽核。

最終 live membership＝0、ACTIVE password credential＝0、ACTIVE App Session＝0；兩個新 Actor
停用，identity／credential／session 撤銷。私密 fixture 移除 accounts/password，保留 retired marker。
Core PID 11596／17724 與 frontend PID 18704 已停止，3000／8000 無 listener。
未修改既有 demo 登入、既有 scope 或 schema。Core 全套 unit **1,388 passed**（含 13 個新 fixture
安全案例）、QA helper Ruff check／format、Node syntax 與 git diff check 通過；production build 已重新完成。
新 helper CI 由收尾 PR 追蹤，不將前述產品基準 main CI 冒充新 helper 的 CI 證據。

最後 writer-expiry 的 JSON 早期將「他人派案 404」命名為 completed-visit denial；腳本標籤已修正。
完成後本人存取拒絕的證據來自先前 reader 接續階段與 DB 讀回，不使用 writer 的該次 404 推論。

本次完成這兩個增量的本機 real-auth 讀寫驗收，不等於完整 US-C01／Wave 2 或 production readiness。
