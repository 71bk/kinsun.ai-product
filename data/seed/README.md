# 合成 Demo Seed

這裡的資料全部是虛擬 Persona，不含真實長者資料。固定 ID 與測試可讀 Mapping 在
`demo_ids.json`。

從 repository 根目錄重建本機 Demo 資料：

```powershell
.\scripts\reset_demo.ps1 -ConfirmLocalReset
```

這個命令會刪除並重建 `eldercare_ai` schema，只允許
`APP_ENV=development`、localhost 且 database 名稱為 `kinsun`。不會對 staging、
production 或 `kinsun_test` 執行。

Seed 固定提供：

- 林阿嬤、張阿姨、陳伯伯三位合成人物。
- 幸福日照中心與陳伯伯當日有效居服派案。
- 林阿嬤已確認且 ACTIVE 的「女兒小美／每週日通話」記憶。
- Draft、Published、Withdrawn 三份家屬報表。
- Sent 與可重試 Failed 通知。
- Graph projection failed、Notification failed、Consent revoked 故障狀態。

AWS EventBridge、SQS、Neptune 與通知 Provider 仍須依 Owner 決策綁定；Seed 只建立
Aurora Source of Truth 與可重放／降級證據，不代表外部服務已上線。
