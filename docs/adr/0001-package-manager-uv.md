# ADR 0001：Python 套件與環境管理採用 uv

- 狀態：Accepted
- 日期：2026-07-30
- 決策者：專案 Owner
- 相關文件：12｜實作計畫、環境、團隊分工與交付路線 v0.1；13｜Database Migration、Release 與 Rollback v0.1
- 取代：AGENTS.md §11 之「Package／Workspace Manager」待決事項

## 背景

AGENTS.md §9 規定在核准前不得自行鎖定 Package Manager，§11 將其列為待 ADR 項目。
建立 Alembic migration 需要一個可重現的 Python 環境，因此必須先收斂這個選擇。

文件 13 §十九要求 Migration Job 與 Core API 使用「相同的程式版本與 Dependency Lock」，
所以工具必須產生可提交的 lock file。

## 候選方案

| 方案 | 優點 | 缺點 |
| --- | --- | --- |
| **uv** | 解析與安裝快；`uv.lock` 跨平台可重現；內建 Python 版本管理（`.python-version`）；官方容器映像可直接 `COPY --from` | 相對年輕，生態系仍在變動 |
| pip + requirements.txt | 零額外工具，最中立 | 版本鎖定需另外用 pip-compile；無內建 Python 版本管理 |
| Poetry | 成熟的 lock 與 workspace 支援 | 需額外安裝；解析速度明顯較慢 |

## 決策

採用 **uv**。

- 開發機已安裝 uv 0.11.25。
- `services/core-api/.python-version` 固定 3.12，與容器的 `python:3.12-slim-bookworm` 一致，
  避免本機 3.13、容器 3.12 這種難查的行為差異。
- `uv.lock` 必須進版控。
- Migration Job 映像用 `uv sync --locked --no-dev`，lock 對不上就直接失敗，
  滿足文件 13 對 Dependency Lock 的要求。

## 影響

- 新開發者需先安裝 uv（`winget install astral-sh.uv` 或 `pipx install uv`）。
- 此決策僅涵蓋套件管理。**Python Web Framework 仍未決定**；
  `services/core-api/pyproject.toml` 刻意不含 FastAPI 或 Django，
  只保留 alembic、sqlalchemy、psycopg 三個資料層依賴。
- 若日後改用其他工具，`pyproject.toml` 的 `[project.dependencies]` 是標準格式，可直接沿用。

## 待後續處理

- Python Web Framework 的 ADR（AGENTS.md §11 仍列為待決）。
- CI 的 lint、type check、test 指令尚未建立（AGENTS.md §10）。
