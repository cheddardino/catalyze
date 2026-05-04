"""SQLite store for detection events. Single-file db at captures/catalyze.db.

WAL mode lets the API read concurrently with the detection-loop writer.
Each call opens its own short-lived connection — sqlite3 connections are
not safe to share across threads, and the per-connection cost is small.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import migrations

_DB_PATH: Optional[Path] = None

_VALID_SEVERITY = ("normal", "warning", "critical")


def init(db_path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(db_path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        migrations.apply(conn)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    if _DB_PATH is None:
        raise RuntimeError("db.init(path) must be called first")
    conn = sqlite3.connect(str(_DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous  = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_detection(
    timestamp: str,
    image_full: str,
    image_crop: Optional[str],
    image_overlay: Optional[str],
    image_cat: Optional[str],
    bbox: Any,
    color_pcts: Dict[str, float],
    remark: str,
    severity: str,
    model_version: Optional[str] = None,
    kind: str = "poop",
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO detections
               (timestamp, kind, image_full, image_crop, image_overlay, image_cat,
                bbox_json, red_pct, yellow_pct, green_pct, brown_pct,
                remark, severity, model_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                kind,
                image_full,
                image_crop,
                image_overlay,
                image_cat,
                json.dumps(bbox) if bbox is not None else None,
                color_pcts.get("red"),
                color_pcts.get("yellow"),
                color_pcts.get("green"),
                color_pcts.get("brown"),
                remark,
                severity,
                model_version,
            ),
        )
        return cur.lastrowid


def list_detections(
    limit: int = 50,
    offset: int = 0,
    since: Optional[str] = None,
    until: Optional[str] = None,
    severity: Optional[str] = None,
    kind: Optional[str] = None,
) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM detections WHERE 1=1"
    params: list = []
    if since is not None:
        sql += " AND timestamp >= ?"
        params.append(since)
    if until is not None:
        sql += " AND timestamp < ?"
        params.append(until)
    if severity is not None:
        sql += " AND severity = ?"
        params.append(severity)
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_detection(detection_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM detections WHERE id = ?", (detection_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def stats_by_day(days: int = 30) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            date(timestamp) AS date,
            count(*)        AS n_events,
            avg(red_pct)    AS avg_red_pct,
            avg(yellow_pct) AS avg_yellow_pct,
            avg(green_pct)  AS avg_green_pct,
            avg(brown_pct)  AS avg_brown_pct,
            sum(CASE WHEN severity='normal'   THEN 1 ELSE 0 END) AS n_normal,
            sum(CASE WHEN severity='warning'  THEN 1 ELSE 0 END) AS n_warning,
            sum(CASE WHEN severity='critical' THEN 1 ELSE 0 END) AS n_critical
        FROM detections
        WHERE timestamp >= date('now', ?)
        GROUP BY date(timestamp)
        ORDER BY date DESC
    """
    with _connect() as conn:
        rows = conn.execute(sql, (f"-{int(days)} days",)).fetchall()
        return [dict(r) for r in rows]


def health() -> Dict[str, Any]:
    try:
        with _connect() as conn:
            last = conn.execute(
                "SELECT timestamp FROM detections ORDER BY id DESC LIMIT 1"
            ).fetchone()
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        return {
            "db_ok": True,
            "last_event_at": last[0] if last else None,
            "schema_version": version,
        }
    except sqlite3.Error as e:
        return {"db_ok": False, "error": str(e), "last_event_at": None, "schema_version": None}


def list_unsynced(limit: int = 20) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM detections WHERE synced = 0 ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def mark_synced(
    local_id: int,
    supabase_id: Optional[str],
    img_full_url: Optional[str],
    img_crop_url: Optional[str],
    img_overlay_url: Optional[str],
    img_cat_url: Optional[str],
) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE detections SET
                synced = 1, supabase_id = ?,
                img_full_url = ?, img_crop_url = ?, img_overlay_url = ?, img_cat_url = ?
               WHERE id = ?""",
            (supabase_id, img_full_url, img_crop_url, img_overlay_url, img_cat_url, local_id),
        )


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("bbox_json"):
        try:
            d["bbox"] = json.loads(d.pop("bbox_json"))
        except json.JSONDecodeError:
            d.pop("bbox_json")
    return d
