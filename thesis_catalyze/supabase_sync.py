"""Background thread: upload unsynced local detections to Supabase.

Write path: local SQLite (always, instant, offline-safe).
Sync path:  this module drains unsynced rows to Supabase when WiFi is up.
            Images go to Supabase Storage; only the public URL lands in Postgres.

The thread retries indefinitely — a row stays unsynced until it succeeds.
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
import requests
from supabase import create_client, Client

import db
import json

load_dotenv()

SYNC_INTERVAL_S = 30
BATCH_SIZE = 20
STORAGE_BUCKET = "captures"
ALERT_SEVERITIES = {"warning", "critical"}

_client: Optional[Client] = None
_client_lock = threading.Lock()


def _get_client() -> Optional[Client]:
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        url = os.environ.get("SUPABASE_URL")
        # Prefer service role key for server-side sync to bypass RLS; fall back to SUPABASE_KEY
        key = (
            os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
        )
        if not url or not key:
            print("[sync] SUPABASE_URL / SUPABASE_KEY not set — sync disabled", flush=True)
            return None
        try:
            _client = create_client(url, key)
        except Exception as e:
            print(f"[sync] failed to init Supabase client: {e}", flush=True)
        return _client


def _get_function_url() -> Optional[str]:
    url = os.environ.get("SUPABASE_URL")
    if not url:
        return None
    return f"{url.rstrip('/')}/functions/v1/notify-detection"


def _get_function_headers() -> Optional[dict[str, str]]:
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
    )
    if not key:
        return None
    return {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": "application/json",
    }


def _notify_warning_detection(row: dict, supabase_row: Optional[dict]) -> None:
    severity = row.get("severity")
    if severity not in ALERT_SEVERITIES:
        return

    function_url = _get_function_url()
    headers = _get_function_headers()
    if not function_url or not headers:
        print("[sync] alert email skipped: Supabase function config missing", flush=True)
        return

    record = {
        "id": (supabase_row or {}).get("id") or row.get("supabase_id") or row.get("local_id"),
        "timestamp": row.get("timestamp"),
        "kind": row.get("kind"),
        "severity": severity,
        "remark": row.get("remark"),
    }

    try:
        res = requests.post(function_url, headers=headers, json={"record": record}, timeout=15)
        if res.ok:
            print(f"[sync] alert email sent for row {row.get('id')} severity={severity}", flush=True)
        else:
            print(f"[sync] alert email failed for row {row.get('id')}: {res.status_code} {res.text}", flush=True)
    except Exception as e:
        print(f"[sync] alert email error for row {row.get('id')}: {e}", flush=True)


def _upload_image(client: Client, local_path: str, row_id: int, suffix: str) -> Optional[str]:
    """Upload one image file to Supabase Storage, return its public URL."""
    p = Path(local_path)
    if not p.exists():
        print(f"[sync] {suffix} image missing: {local_path}", flush=True)
        return None
    storage_key = f"{row_id}/{p.stem}_{suffix}{p.suffix}"
    try:
        with open(p, "rb") as f:
            client.storage.from_(STORAGE_BUCKET).upload(
                path=storage_key,
                file=f,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
        url = client.storage.from_(STORAGE_BUCKET).get_public_url(storage_key)
        print(f"[sync] {suffix} uploaded: {url}", flush=True)
        return url
    except Exception as e:
        print(f"[sync] image upload failed ({storage_key}, {suffix}): {e}", flush=True)
        return None


def _sync_batch(client: Client, captures_dir: Path) -> int:
    """Fetch up to BATCH_SIZE unsynced rows, upload them, return count synced."""
    rows = db.list_unsynced(limit=BATCH_SIZE)
    if not rows:
        return 0

    synced = 0
    for row in rows:
        rid = row["id"]
        try:
            print(f"[sync] row {rid}: image_cat={row.get('image_cat')}, has pending_cat={bool(row.get('image_cat'))}", flush=True)
            # full image stays local only — auto-deleted after 7 days by maintenance.py
            full_url  = None
            crop_url  = _upload_image(client, str(captures_dir / row["image_crop"]),  rid, "crop")  if row.get("image_crop")    else None
            over_url  = _upload_image(client, str(captures_dir / row["image_overlay"]),rid,"overlay")if row.get("image_overlay") else None
            cat_url   = _upload_image(client, str(captures_dir / row["image_cat"]),   rid, "cat")    if row.get("image_cat")     else None

            payload = {
                "local_id":     rid,
                "timestamp":    row["timestamp"],
                "kind":         row.get("kind", "poop"),
                # row returned by db.list_unsynced contains `bbox` (parsed JSON);
                # convert it to a JSON string field expected by Postgres.
                "bbox_json":    json.dumps(row.get("bbox")) if row.get("bbox") is not None else None,
                "red_pct":      row.get("red_pct"),
                "yellow_pct":   row.get("yellow_pct"),
                "green_pct":    row.get("green_pct"),
                "brown_pct":    row.get("brown_pct"),
                "remark":       row.get("remark"),
                "severity":     row.get("severity"),
                "model_version":row.get("model_version"),
                "image_full":   full_url,
                "image_crop":   crop_url,
                "image_overlay":over_url,
                "image_cat":    cat_url,
            }
            resp = client.table("detections").insert(payload).execute()
            supabase_id = resp.data[0]["id"] if resp.data else None
            db.mark_synced(rid, supabase_id, full_url, crop_url, over_url, cat_url)
            _notify_warning_detection(row, resp.data[0] if resp.data else None)
            synced += 1
        except Exception as e:
            print(f"[sync] row {rid} failed: {e}", flush=True)

    return synced


def sync_loop(captures_dir: Path, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        client = _get_client()
        if client:
            try:
                n = _sync_batch(client, captures_dir)
                if n:
                    print(f"[sync] uploaded {n} detection(s) to Supabase", flush=True)
            except Exception as e:
                print(f"[sync] tick error: {e}", flush=True)
        stop_event.wait(SYNC_INTERVAL_S)


def start(captures_dir: Path) -> Tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    t = threading.Thread(
        target=sync_loop,
        args=(captures_dir, stop_event),
        daemon=True,
        name="supabase-sync",
    )
    t.start()
    return t, stop_event
