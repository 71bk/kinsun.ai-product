"""baseline eldercare_ai schema v0 1

把 smart_eldercare_schema_v0_1.sql 收進 Alembic 版本控制的第一版。

做法：把該 SQL 原封不動凍結成 versions/sql/ 底下的快照，migration 直接執行它。
48 張表、10 個 ENUM、54 個 index、46 個 function/trigger 與全部 COMMENT ON 都原樣保留，
不經過 SQLAlchemy 轉譯，所以不會在翻譯過程掉東西。

規則（見 docs/adr/0002-alembic-baseline-strategy.md）：
- 快照檔一旦被套用就視為不可變。要改 schema 請新增 revision，不要動這個檔案。
- EXPECTED_SHA256 會在每次 upgrade 前驗證，快照被改到就直接失敗。
- 因為沒有 SQLAlchemy models，`alembic revision --autogenerate` 目前不可用，
  後續 revision 需手寫 op.execute() 或 op.create_table()。

Revision ID: f393b4452ce8
Revises:
Create Date: 2026-07-30 15:02:09.827396+00:00

"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f393b4452ce8"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA_NAME = "eldercare_ai"

SNAPSHOT_PATH = Path(__file__).parent / "sql" / f"{Path(__file__).stem}.sql"

# 對應 smart_eldercare_schema_v0_1.sql（122058 bytes）在凍結當下的內容
EXPECTED_SHA256 = "2ed62d8729b7cbb6c59c69b4be0ab6b4aeed10b0ac2888d1bbbca2c352087def"

# 快照最外層有一組 BEGIN; / COMMIT;，但交易由 Alembic 自己管，留著會讓
# Alembic 在寫 alembic_version 之前就把交易提交掉。這裡只拿掉「整行且帶分號」的
# 那兩行；DO $$ ... $$ 與 plpgsql 函式裡的 15 個裸 BEGIN 不帶分號，不會被誤刪。
_TRANSACTION_CONTROL = re.compile(
    r"^[ \t]*(?:BEGIN|COMMIT)[ \t]*;[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


def _load_snapshot_sql() -> str:
    if not SNAPSHOT_PATH.is_file():
        raise RuntimeError(f"baseline 快照不存在：{SNAPSHOT_PATH}")

    # 一定要指定 utf-8：Windows 的預設編碼是 cp950，會讀壞中文 COMMENT。
    raw_sql = SNAPSHOT_PATH.read_text(encoding="utf-8")

    actual_sha256 = hashlib.sha256(SNAPSHOT_PATH.read_bytes()).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(
            "baseline 快照已被修改，拒絕套用。\n"
            f"  檔案: {SNAPSHOT_PATH}\n"
            f"  期望: {EXPECTED_SHA256}\n"
            f"  實際: {actual_sha256}\n"
            "已套用的 migration 必須不可變。schema 要改請新增一個 revision。"
        )

    return _TRANSACTION_CONTROL.sub("", raw_sql)


def upgrade() -> None:
    """建立 eldercare_ai schema 的 v0.1 完整結構。"""
    # 這裡刻意繞過 SQLAlchemy，直接拿 psycopg 的 cursor 執行。
    #
    # op.execute() / exec_driver_sql() 都會帶一組空參數進 psycopg，psycopg 就會把
    # 語句當成有 placeholder 來解析，於是 plpgsql 函式裡 RAISE EXCEPTION 的
    # 'Table %.%' 會被判成非法 placeholder 而失敗。把 % 改成 %% 雖然也能過，
    # 但那會動到快照內容、跟 SHA-256 驗證的用意相衝突。
    #
    # cursor.execute(sql) 不帶 params 時 psycopg 原樣送出，並使用 simple query
    # protocol，剛好也支援一次送多段語句。cursor 取自同一條連線，仍在 Alembic
    # 的交易裡，失敗會整批 rollback。
    raw_connection = op.get_bind().connection.driver_connection
    with raw_connection.cursor() as cursor:
        cursor.execute(_load_snapshot_sql())


def downgrade() -> None:
    """整個 schema 砍掉。

    這是 baseline，往下退就是回到「什麼都沒有」，所以會連同 48 張表、ENUM、
    trigger 與資料一起消失。CI 與本機重建用；正式環境請走文件 13 的 Restore 流程。

    alembic_version 在 public schema，不會被這裡的 CASCADE 波及。
    pgcrypto 也留著，它由 docker/postgres/init 建立、非本 migration 所有。
    """
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE")
