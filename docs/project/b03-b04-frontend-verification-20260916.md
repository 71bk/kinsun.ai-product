# B03／B04 前端接線核對 — 2026-09-16

## 結論與修正

已核對 UI commit `63f1a9d` 的類型／時間修正及來源篩選接線。首次相關 Vitest 41 tests
通過，但 typecheck 失敗：兩份新增測試以零參數 `vi.fn` 建立 mock，再讀取呼叫參數，
TypeScript 因空 tuple 回報 TS2352／TS2493，阻擋 production build。

已在 `EventReviewControls.test.ts` 與 `events.test.ts` 補上 Vitest 1 支援的參數 tuple／
回傳值型別，並將注意事項記錄於 AGENTS／CLAUDE。首次嘗試新版單一函式 generic 亦被
Vitest 1 型別拒絕，已改正。產品接線與 runtime code 未修改。

## 本次重驗

| 項目 | 結果 |
| --- | --- |
| 相關回歸 | 初次 5 files／41 tests passed；型別修正後兩份測試 16 tests passed |
| Frontend typecheck | 通過 |
| Production build | 通過；Next 16.2.12 |
| ESLint | 通過 |
| 瀏覽器修正請求 | CORRECT 送 SLEEP、`2026-09-16T13:30:00.000Z`、原 payload 與 expected_version=1 |
| 時間語意 | 畫面台北時間 21:30 轉 UTC 13:30；清除既有時間送 null；未改值由單元測試驗證省略 |
| 來源／分頁 | 先載入帶 cursor 的下一頁，再選 MANUAL，請求不帶舊 cursor |
| 條件交集／重置 | MANUAL 與 NEEDS_REVIEW 同時送出；清除後請求只有 limit=100 |
| 409 | 顯示重新載入提示、關閉確認框、保留修正草稿 |
| 403 | 卸載長者姓名、事件、草稿與確認框，只保留無權限提示 |
| 畫面 | 375×812、390×844、430×932、1440×900；修正表單逐張看圖，DOM 水平溢出檢查通過 |

瀏覽器使用本次 production build，測試服務 `127.0.0.1:3106`。API 在瀏覽器中攔截並
回覆合成 fixture，測試成功回應只驗證 request／UI 流程，不作為資料持久化證據。
截圖為 `.qa/local/b03-confirm-{375,390,430,1440}.png`，保留本機且不進 Git。
手機欄位、清除時間核取方塊與送出按鈕完整可見；桌面篩選列與修正表單無重疊。

初次瀏覽器檢查遇到 selector 與非同步等待造成的假失敗：改用可存取角色名稱定位
select／textarea，清除篩選改等待實際 request 後重驗通過；沒有為此修改產品程式。

## 範圍限制與下一步

獨立檢查本機 Core 8000 的 health／ready 均為 200，資料庫 connected，OpenAPI 包含
B03 修正欄位與 B04 source_type。Supabase migration 已由前一個工作完成。
本次沒有登入後寫入 DB，不能將 Browser fixture PASS 視為 Browser → BFF → Core →
Supabase 全鏈路驗收，也未重跑全套 frontend／backend tests 或遠端 CI。

下一步使用隔離的合成 campaign 做真實登入／持久化驗收；修正歷史瀏覽、來源片段導覽、
匯出與完整 B03／B04／Wave 2 closeout 仍不在本次完成範圍。
