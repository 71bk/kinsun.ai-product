# 需求對照

| 需求 | 實作 | 驗證 |
| --- | --- | --- |
| 1 即時授權 | ElderProfileService.authorize、authorization repositories | SQL role/tenant/scope/time/enrollment cases；unit lock-wait denial |
| 2 查看與維護 | elder_profiles router、ElderProfilePanel | 真實登入 BFF UI lifecycle；frontend tests |
| 3 來源與歷史 | ElderProfileChange、care_snapshot | SQL VERIFIED correction、DISPUTED/RETIRED、before/after |
| 4 版本、冪等、交易 | mutate、Elder row lock、IdempotencyRepository、outbox | SQL snapshots/counts；並行 200/409、201/201 同 ID |
| 5 分頁與介面 | care_list/history、panel、profile messages | cursor SQL；中英 RWD、七個元件測試 |
| 6 建立人 scope | onboarding service、migration e9a1b3c5d768 | 實際 migration SQL exact/default 與 restricted cases |
| 7 延後語音 | 未修改語音流程 | 見交付紀錄範圍 |

完整結果：[交付紀錄](../../../docs/project/staff-elder-profile-maintenance-20260930.md)。
