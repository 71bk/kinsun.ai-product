#!/bin/bash
# 另外建立測試用資料庫，讓 integration test 不污染開發資料。
set -euo pipefail

TEST_DB="${POSTGRES_DB}_test"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE DATABASE "${TEST_DB}" OWNER "${POSTGRES_USER}";
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$TEST_DB" <<-EOSQL
	CREATE EXTENSION IF NOT EXISTS pgcrypto;
	CREATE EXTENSION IF NOT EXISTS citext;
EOSQL

echo "created test database: ${TEST_DB}"
