---
inclusion: always
---

# Technology Stack

目前可執行方式與指令：
#[[file:README.md]]

架構與技術決策：
#[[file:AGENTS.md]]
#[[file:docs/08智慧長照 AI 陪伴系統－AWS 系統架構、服務選型與 ADR v0.1.md]]

## 已實作

- Python 3.12。
- `services/core-api`：FastAPI、SQLAlchemy 2 async、Pydantic、Alembic、PostgreSQL。
- `services/agent-runtime`：FastAPI、Pydantic、單輪 Orchestrator、Mock Model Provider、
  deterministic Safety Evaluator。
- 兩個服務分別使用自己的 `pyproject.toml`、`uv.lock` 與 uv environment。
- OpenAPI 3.1 與 JSON Schema 放在 `contracts/`，並有靜態與 live 驗證腳本。
- 本機資料層使用 Docker Compose 與 PostgreSQL 16。

## Target Architecture，不代表已實作

- ECS/Fargate、API Gateway、Cognito。
- Bedrock AgentCore、Bedrock Models、Guardrails。
- Aurora PostgreSQL、Neptune Serverless、OpenSearch Serverless、S3。
- EventBridge、SQS/DLQ、Step Functions、Scheduler、SES、LINE Adapter。

產生程式碼或文件時必須明確區分「目前存在」與「目標規劃」，不得把 AWS 架構圖中的服務
描述成 repository 已可執行的功能。

## 指令慣例

- 套件與命令透過 `uv` 執行。
- Core API unit tests：`uv run --project services/core-api pytest services/core-api/tests/unit`。
- Agent Runtime tests：`uv run --directory services/agent-runtime pytest`。必須切換工作目錄，避免
  Agent Runtime 的 Pydantic Settings 誤讀 repository root 的 Core API `.env`。
- 不直接使用 Alembic `--autogenerate`；先依 `AGENTS.md` 檢查 baseline 與 model 覆蓋率。
