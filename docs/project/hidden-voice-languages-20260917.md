# 長者語音選項隱藏與畫面驗證

- 日期：2026-09-17。
- 基底：origin/main `dd65e2f`；分支 `fix/hide-unavailable-voice-languages-20260917`。
- 狀態：本機實作與驗證完成；未部署。

長者語音選單移除尚未驗證的台語、客語按鈕，以及「目前可以聽懂」提示。
保留國語與 English；重新載入預設國語，選擇值沒有持久化。
後端語言路由、長者語言偏好資料與開發語音測試頁維持原狀。

## 驗證

- 既有 VoiceHomeClient 與 voice library 測試共 19 項通過。
- 最終 production build（包含 TypeScript）通過；LanguageSelect ESLint、diff check 通過。
- 依 playwright-visual-qa skill，在 production build 的 3110 本機服務進行合成 UI QA。
  Session 與 Consent 回應由瀏覽器攔截，沒有錄音、真實登入、Core 寫入或語音供應商呼叫。
- 375／390／430／1440 viewport 的語言選單均只有國語與 English，兩者點選狀態正確。
  另檢查 390 reduced-motion；最終五張截圖均已人工檢視。
- 此工作站 requested 375／390／430 的實測 innerWidth 分別為 376／391／431；
  扣除 scrollbar 後 clientWidth 為 361／376／416，scrollWidth 與 clientWidth 相同。
  1440 的 clientWidth／scrollWidth 均為 1425。

首次畫面驗證發現 375／390 原有橫向溢出：CompanionCharacter 的手機尺寸規則出現在
桌面基礎規則之前，同 specificity 導致手機寬度被 300px 蓋過。這是實際 CSS cascade 問題，
不是動畫或舊 bundle。將既有 media query 移至基礎規則之後，重新 build／restart，
使用新的 query 重新導覽，四種尺寸均無水平溢出。

截圖：`.qa/local/hidden-voice-languages-final-{375,390,430,1440,reduced}.png`。
修改檔：`LanguageSelect.tsx`、`CompanionCharacter.module.css`；協作文件補記成功 fixture 的
完整 meta 要求。未驗證真機、麥克風、ASR／TTS 品質；本次不宣稱國語／英文語音服務已驗收。
