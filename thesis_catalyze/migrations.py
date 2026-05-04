"""Versioned schema migrations for the Catalyze SQLite database.

Each entry in MIGRATIONS is a multi-statement SQL string applied in order.
PRAGMA user_version tracks how many migrations have been applied.

To add a migration: append a new SQL string. Never edit or reorder existing
entries — they may already have run on a Pi in the field.
"""

import sqlite3
from typing import List

MIGRATIONS: List[str] = [
    # v1 — initial schema. Idempotent so it's a no-op on legacy DBs that
    # were created before user_version tracking existed.
    """
    CREATE TABLE IF NOT EXISTS detections (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp     TEXT    NOT NULL,
        image_full    TEXT,
        image_crop    TEXT,
        image_overlay TEXT,
        bbox_json     TEXT,
        color_json    TEXT,
        remark        TEXT,
        severity      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(timestamp DESC);
    """,

    # v2 — typed color columns, kind, model_version, severity index;
    # backfill from color_json then drop it.
    """
    ALTER TABLE detections ADD COLUMN kind TEXT NOT NULL DEFAULT 'poop';
    ALTER TABLE detections ADD COLUMN red_pct REAL;
    ALTER TABLE detections ADD COLUMN yellow_pct REAL;
    ALTER TABLE detections ADD COLUMN green_pct REAL;
    ALTER TABLE detections ADD COLUMN brown_pct REAL;
    ALTER TABLE detections ADD COLUMN model_version TEXT;
    UPDATE detections SET
        red_pct    = json_extract(color_json, '$.red'),
        yellow_pct = json_extract(color_json, '$.yellow'),
        green_pct  = json_extract(color_json, '$.green'),
        brown_pct  = json_extract(color_json, '$.brown')
     WHERE color_json IS NOT NULL;
    ALTER TABLE detections DROP COLUMN color_json;
    CREATE INDEX IF NOT EXISTS idx_detections_severity
        ON detections(severity, timestamp DESC);
    """,

    # v3 — Supabase sync tracking columns.
    """
    ALTER TABLE detections ADD COLUMN synced INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE detections ADD COLUMN supabase_id TEXT;
    ALTER TABLE detections ADD COLUMN img_full_url TEXT;
    ALTER TABLE detections ADD COLUMN img_crop_url TEXT;
    ALTER TABLE detections ADD COLUMN img_overlay_url TEXT;
    CREATE INDEX IF NOT EXISTS idx_detections_synced ON detections(synced, id);
    """,

    # v4 — keep cat image path and synced cat image URL paired with poop rows.
    """
    ALTER TABLE detections ADD COLUMN image_cat TEXT;
    ALTER TABLE detections ADD COLUMN img_cat_url TEXT;
    """,
]


def apply(conn: sqlite3.Connection) -> int:
    """Apply any pending migrations. Returns the resulting user_version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    target = len(MIGRATIONS)
    for i in range(current, target):
        sql = "BEGIN;\n" + MIGRATIONS[i] + f"\nPRAGMA user_version = {i + 1};\nCOMMIT;"
        try:
            conn.executescript(sql)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
    return target
