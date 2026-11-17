from __future__ import annotations
import sqlite3
from app.config import DB_PATH

SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  face_value REAL NOT NULL,
  min_spend REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS redeem_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL UNIQUE,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  occurred_at TEXT NOT NULL DEFAULT '',
  batch_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open'
);
-- 批头：快照 as_of 钉钟与纳入/截断笔数，sealed 后不再被任何晚到事件改写。
CREATE TABLE IF NOT EXISTS redeem_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_day TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT,
  as_of TEXT NOT NULL DEFAULT '',
  cutoff_policy TEXT NOT NULL DEFAULT 'as_of_prefix',
  truncated_count INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);
-- 批明细：钉扎瞬间纳入集合的不可变快照（与 fact 状态解耦，晚到事件无法改写）。
CREATE TABLE IF NOT EXISTS redeem_batch_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  fact_id INTEGER NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL DEFAULT '',
  UNIQUE(batch_id, fact_id)
);
'''

# 旧库增量迁移：只补不改，历史行的语义默认值与 as_of_prefix 对齐。
_MIGRATIONS = (
    ("redeem_facts", "occurred_at", "ALTER TABLE redeem_facts ADD COLUMN occurred_at TEXT NOT NULL DEFAULT ''"),
    ("redeem_batches", "as_of", "ALTER TABLE redeem_batches ADD COLUMN as_of TEXT NOT NULL DEFAULT ''"),
    ("redeem_batches", "cutoff_policy", "ALTER TABLE redeem_batches ADD COLUMN cutoff_policy TEXT NOT NULL DEFAULT 'as_of_prefix'"),
    ("redeem_batches", "truncated_count", "ALTER TABLE redeem_batches ADD COLUMN truncated_count INTEGER NOT NULL DEFAULT 0"),
)


def connect(immediate: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        for table, column, ddl in _MIGRATIONS:
            if not _has_column(conn, table, column):
                conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()
