-- 只建立 extension，不建表。
-- 依 13 文件，Schema 由 Alembic（FastAPI 路線）或 Django Migrations 管理，
-- init script 不得成為第二個 schema 來源。

-- token_hash、digest 等雜湊需求（Secure Link）
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 大小寫不敏感文字（email、identifier 類欄位）
CREATE EXTENSION IF NOT EXISTS citext;
