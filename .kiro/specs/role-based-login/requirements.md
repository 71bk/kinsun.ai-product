# 需求文件：角色式登入與導向系統

## 簡介

角色式登入與導向系統為智慧長照 AI 陪伴系統的入口模組，負責依使用者角色提供差異化的登入體驗與頁面導向。系統於首頁提供三個登入入口（長者／家屬、居服員、管理者），透過 Google 與 LINE 聯合身分供應商進行 OAuth 驗證，並依據後端預先指派的角色將使用者導向對應介面。系統須兼顧長者的無障礙操作需求與多角色的安全隔離。

## 詞彙表

- **System（系統）**：角色式登入與導向系統整體
- **Landing_Page（首頁）**：使用者進入應用程式後首先看到的角色選擇頁面
- **Entry_Point（登入入口）**：Landing_Page 上供使用者選擇的角色入口按鈕
- **Auth_Service（驗證服務）**：整合 Amazon Cognito 並支援 Google 與 LINE 聯合身分供應商的驗證元件
- **Role_Resolver（角色解析器）**：於驗證成功後查詢 DynamoDB 中使用者角色並決定導向目標的元件
- **Router（路由器）**：Next.js 前端路由元件，負責執行頁面導向與路徑保護
- **Admin_Panel（管理面板）**：系統管理者使用的後台管理介面
- **User_Record（使用者紀錄）**：DynamoDB 中記錄使用者角色與帳號對應關係的資料項目
- **Elder（長者）**：透過語音互動介面與系統互動的主要使用者
- **Family_Member（家屬）**：查看長者生活摘要的相關人員
- **Caregiver（照護者／居服員）**：負責照護多位長者並使用照護者儀表板的人員
- **Admin（系統管理者）**：負責系統設定、角色指派與知識庫管理的人員
- **OAuth_Provider（OAuth 供應商）**：Google 或 LINE 聯合身分供應商
- **Pending_Status（待審核狀態）**：使用者已完成驗證但尚未被指派角色的狀態
- **PWA**：Progressive Web App，系統前端應用程式（Next.js）

## 需求

---

### 需求 1：Landing Page 三入口顯示

**使用者故事：** 身為使用者，我希望開啟應用程式時能清楚看到適合我的登入入口，以便快速進入對應的功能介面。

#### 驗收條件

1. THE Landing_Page SHALL 顯示三個 Entry_Point 按鈕：「長者／家屬」、「居服員」、「管理者」
2. THE Landing_Page SHALL 將「長者／家屬」Entry_Point 設計為最大尺寸且使用溫暖色調，以引導長者優先識別
3. THE Landing_Page SHALL 確保所有 Entry_Point 按鈕的觸控目標區域不小於 48×48 像素
4. THE Landing_Page SHALL 同時支援行動裝置瀏覽器與桌面瀏覽器之顯示與操作
5. THE Landing_Page SHALL 於未登入狀態下不顯示任何使用者個人資訊

---

### 需求 2：Google 與 LINE OAuth 登入流程

**使用者故事：** 身為使用者，我希望能使用 Google 或 LINE 帳號登入系統，以便不需記憶額外的帳號密碼。

#### 驗收條件

1. WHEN 使用者選擇任一 Entry_Point 後，THE System SHALL 顯示「使用 Google 登入」與「使用 LINE 登入」兩個 OAuth 登入選項
2. WHEN 使用者點擊 OAuth 登入選項，THE Auth_Service SHALL 將使用者導向對應 OAuth_Provider 的授權頁面
3. WHEN OAuth_Provider 回傳授權成功，THE Auth_Service SHALL 透過 Amazon Cognito 完成 Token 交換並建立使用者 Session
4. IF OAuth_Provider 回傳授權失敗或使用者取消授權，THEN THE System SHALL 顯示錯誤訊息並將使用者導回 Landing_Page
5. THE Auth_Service SHALL 記錄使用者選擇之 Entry_Point 資訊於 Session 中，供後續角色驗證使用

---

### 需求 3：驗證後角色解析與頁面導向

**使用者故事：** 身為使用者，我希望登入後自動被導向到適合我角色的頁面，以便立即開始使用系統功能。

#### 驗收條件

1. WHEN Auth_Service 完成驗證，THE Role_Resolver SHALL 依據使用者之 email 或 LINE ID 查詢 DynamoDB 中對應之 User_Record 取得角色資訊
2. WHEN User_Record 之角色為 elder 且使用者透過「長者／家屬」Entry_Point 登入，THE Router SHALL 將使用者導向語音互動介面
3. WHEN User_Record 之角色為 family 且使用者透過「長者／家屬」Entry_Point 登入，THE Router SHALL 將使用者導向家屬摘要頁面
4. WHEN User_Record 之角色為 caregiver 且使用者透過「居服員」Entry_Point 登入，THE Router SHALL 將使用者導向照護者儀表板
5. WHEN User_Record 之角色為 admin 且使用者透過「管理者」Entry_Point 登入，THE Router SHALL 將使用者導向 Admin_Panel
6. THE Role_Resolver SHALL 於角色解析完成後記錄使用者 ID、角色、登入時間與 Entry_Point 於日誌中

---

### 需求 4：管理者角色預先指派

**使用者故事：** 身為系統管理者，我希望能在後台預先建立使用者帳號並指派角色，以便控制哪些人可以存取系統的哪些功能。

#### 驗收條件

1. THE Admin_Panel SHALL 提供 Admin 建立 User_Record 之功能，包含使用者識別資訊（email 或 LINE ID）與角色欄位
2. THE Admin_Panel SHALL 支援 Admin 指派以下角色之一：elder、family、caregiver、admin
3. THE Admin_Panel SHALL 支援 Admin 修改已建立之 User_Record 的角色欄位
4. THE Admin_Panel SHALL 支援 Admin 停用或刪除已建立之 User_Record
5. THE System SHALL 確保每筆 User_Record 之 email 或 LINE ID 於系統內具備唯一性
6. THE Admin_Panel SHALL 為每次角色指派或變更操作記錄操作者 ID、操作時間與變更內容

---

### 需求 5：入口與角色不匹配處理

**使用者故事：** 身為使用者，我希望在選錯登入入口時收到明確的錯誤提示，以便知道如何正確進入系統。

#### 驗收條件

1. WHEN User_Record 之角色與使用者選擇之 Entry_Point 不匹配，THE System SHALL 顯示錯誤訊息說明該帳號不屬於所選入口之角色類型
2. WHEN 角色與入口不匹配，THE System SHALL 於錯誤訊息中提示使用者返回 Landing_Page 選擇正確入口
3. WHEN 角色與入口不匹配，THE System SHALL 不允許使用者存取該 Entry_Point 對應之功能頁面
4. THE System SHALL 定義以下入口與角色之對應關係：「長者／家屬」入口對應 elder 與 family 角色；「居服員」入口對應 caregiver 角色；「管理者」入口對應 admin 角色

---

### 需求 6：待審核狀態處理

**使用者故事：** 身為使用者，我希望在尚未被指派角色時收到清楚的等待訊息，以便知道我的帳號正在等待管理者審核。

#### 驗收條件

1. WHEN Auth_Service 完成驗證但 Role_Resolver 查無對應之 User_Record，THE System SHALL 顯示 Pending_Status 頁面告知使用者帳號正在等待管理者審核
2. THE Pending_Status 頁面 SHALL 顯示聯繫管理者之資訊或方式
3. WHILE 使用者處於 Pending_Status，THE Router SHALL 禁止該使用者存取任何功能頁面
4. THE System SHALL 允許處於 Pending_Status 之使用者登出並返回 Landing_Page
5. WHEN Admin 為 Pending_Status 之使用者指派角色後，THE System SHALL 於該使用者下次登入時依新指派之角色執行正常導向流程

---

### 需求 7：Session 管理與路由保護

**使用者故事：** 身為系統管理者，我希望未登入的使用者無法直接存取功能頁面，以便確保系統安全性。

#### 驗收條件

1. WHEN 未登入之使用者嘗試直接存取功能頁面 URL，THE Router SHALL 將使用者導回 Landing_Page
2. WHEN 使用者 Session 過期，THE System SHALL 將使用者導回 Landing_Page 並提示重新登入
3. THE System SHALL 提供登出功能，登出後清除使用者 Session 並導回 Landing_Page
4. THE Router SHALL 於每次頁面導向前驗證使用者之 Session 有效性與角色權限

---

### 需求 8：無障礙與多裝置支援

**使用者故事：** 身為長者，我希望登入頁面的按鈕夠大且文字清楚，以便我在視力不佳或不熟悉手機操作的情況下仍能順利登入。

#### 驗收條件

1. THE Landing_Page SHALL 確保所有互動元素符合 WCAG 2.1 AA 等級之色彩對比標準
2. THE Landing_Page SHALL 為所有按鈕與表單元素提供清晰的焦點指示與鍵盤可操作性
3. THE System SHALL 確保登入流程中所有頁面支援螢幕閱讀器之正確解讀
4. THE Landing_Page SHALL 使用響應式設計，於 320px 至 1920px 螢幕寬度範圍內提供適當之版面配置
5. THE Landing_Page SHALL 確保「長者／家屬」Entry_Point 之文字尺寸不小於 18px，其他 Entry_Point 不小於 16px
