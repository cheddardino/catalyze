"""Background thread: pushes the latest camera frame to Supabase Storage every 3 s.

Web app polls the public URL with a cache-busting timestamp → works from any network.
Bucket: live-feed  (public, already created)
Object: latest.jpg  (upserted each cycle)
"""

import os
import threading
import time
from typing import Callable, Optional

import cv2
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

BUCKET       = "live-feed"
OBJECT_PATH  = "latest.jpg"
PUSH_INTERVAL_S = 3
JPEG_QUALITY = 60  # lower = smaller payload, fine for a live preview

_client: Optional[Client] = None
_client_lock = threading.Lock()


def _get_client() -> Optional[Client]:
    global _client
    with _client_lock:
        if _client is not None:
            return _client
        url = os.environ.get("SUPABASE_URL")
        # Prefer service key in backend context; fall back to anon key only if needed.
        key = (
            os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY")
        )
        if not url or not key:
            print("[live-push] SUPABASE_URL / SUPABASE_KEY not set — live push disabled", flush=True)
            return None
        _client = create_client(url, key)
        return _client


def _push_frame(frame, client: Client) -> None:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        return
    data = buf.tobytes()
    client.storage.from_(BUCKET).upload(
        path=OBJECT_PATH,
        file=data,
        file_options={
            "content-type": "image/jpeg",
            "upsert": "true",
            "cache-control": "no-store",
        },
    )


def _loop(frame_provider: Callable, stop: threading.Event) -> None:
    client = _get_client()
    if client is None:
        return

    print(f"[live-push] started — pushing to {BUCKET}/{OBJECT_PATH} every {PUSH_INTERVAL_S}s", flush=True)
    while not stop.is_set():
        try:
            frame = frame_provider()
            if frame is not None:
                _push_frame(frame, client)
        except Exception as exc:
            print(f"[live-push] error: {exc}", flush=True)
        stop.wait(PUSH_INTERVAL_S)

    print("[live-push] stopped", flush=True)


def start(frame_provider: Callable) -> tuple[threading.Thread, threading.Event]:
    """Start the pusher in a daemon thread.

    frame_provider: callable → numpy frame (BGR) or None
    Returns (thread, stop_event) — set stop_event to terminate.
    """
    stop = threading.Event()
    t = threading.Thread(target=_loop, args=(frame_provider, stop), daemon=True, name="live-frame-pusher")
    t.start()
    return t, stop
