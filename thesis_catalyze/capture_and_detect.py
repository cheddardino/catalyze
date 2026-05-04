import argparse
import gc
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from picamera2 import Picamera2
from ultralytics import YOLO

import color_analyzer
import command_poller
import db
import gallon_rotate
import gpio_controller
import live_frame_pusher
import maintenance
import motor
import remark_engine
import supabase_sync
from api import run_in_background as run_api

_HERE         = Path(__file__).parent
CAT_WEIGHTS  = str(_HERE.parent / "yolov8n.pt")
POOP_WEIGHTS = str(_HERE / "best.pt")
CAT_CLASS    = "cat"
STOOL_CLASSES = {"Soft", "Hard", "Watery"}
CAT_CONF     = 0.25   # low — top-view cats score lower in COCO-trained model
POOP_CONF    = 0.20
CAT_IMGSZ    = 320
POOP_IMGSZ   = 640
CAPTURE_DIR  = _HERE.parent / "captures"
DB_PATH      = CAPTURE_DIR / "catalyze.db"
POOP_MODEL_VERSION = f"stool:{Path(POOP_WEIGHTS).name}"

POLL_INTERVAL          = 4     # seconds between inference runs
POST_CLEAN_COOLDOWN    = 30
FALLBACK_POOP_INTERVAL = 120   # fallback poop scan when no cat trigger
CAT_STAY_CAPTURE_S     = 1.5   # capture cat image after this much continuous presence
FULL_CYCLE_SECONDS    = 9.0
FULL_CYCLE_PAUSE_S    = 2.0
FULL_CYCLE_DELAY      = gallon_rotate.STEP_DELAY * 3.0
# Small adjustments for capture-triggered full cycle
FULL_CYCLE_CW_EXTRA_S = 1.0   # add 1s to the CW leg when triggered from capture
FULL_CYCLE_CCW2_S     = 1.0   # final short CCW leg (1s)

# Motor cleaning cycle defaults — delegated to motor.py
MOTOR_DIRECTION = motor.CLEAN_DIRECTION
MOTOR_STEPS     = motor.CLEAN_STEPS
MOTOR_DELAY     = motor.CLEAN_STEP_DELAY
CROP_PADDING    = 20

STATE_COLOR = {
    "MONITORING": (0, 255, 0),    # green
    "OCCUPIED": (0, 255, 255),  # yellow
    "CHECKING": (255, 255, 0),  # cyan
    "DIRTY":    (0, 0, 255),    # red
    "COOLDOWN": (0, 165, 255),  # orange
}


def draw_overlay(frame, state, detections, cooldown_remaining=None):
    disp = frame.copy()
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        label = f"{d['class']} {d['confidence']:.2f}"
        cv2.rectangle(disp, (x1, y1), (x2, y2), STATE_COLOR.get(state, (255, 255, 255)), 2)
        cv2.putText(disp, label, (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, STATE_COLOR.get(state, (255, 255, 255)), 1, cv2.LINE_AA)
    text = f"{state} ({cooldown_remaining}s)" if state == "COOLDOWN" and cooldown_remaining else state
    cv2.putText(disp, text, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, STATE_COLOR.get(state, (255, 255, 255)), 2, cv2.LINE_AA)
    return disp


def _tightest_bbox(detections):
    """Pick the highest-confidence detection's bbox."""
    if not detections:
        return None
    best = max(detections, key=lambda d: d["confidence"])
    return best["bbox"]


def _crop_with_padding(frame, bbox, padding):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(w, x2 + padding)
    y2 = min(h, y2 + padding)
    return frame[y1:y2, x1:x2], [x1, y1, x2, y2]


def save_detection(frame, timestamp, detections, image_cat=None):
    """Save full + cropped + overlay images, run color analysis, write db row.

    Returns the inserted db row id (or None on failure to crop).
    """
    stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    print(f"[save_detection] image_cat={image_cat}", flush=True)
    full_path    = CAPTURE_DIR / f"capture_{stamp}_full.jpg"
    crop_path    = CAPTURE_DIR / f"capture_{stamp}_crop.jpg"
    overlay_path = CAPTURE_DIR / f"capture_{stamp}_overlay.jpg"
    json_path    = CAPTURE_DIR / f"capture_{stamp}.json"

    cv2.imwrite(str(full_path), frame)

    # Derive stool class from the highest-confidence detection
    best_det = max(detections, key=lambda d: d["confidence"]) if detections else {}
    kind = best_det.get("class", "Soft")

    bbox = _tightest_bbox(detections)
    color_pcts = {}
    remark, severity = "No bbox available", "warning"
    crop_bbox = None
    crop_name = None
    overlay_name = None

    if bbox is not None:
        crop, crop_bbox = _crop_with_padding(frame, bbox, CROP_PADDING)
        if crop.size > 0:
            cv2.imwrite(str(crop_path), crop)
            crop_name = crop_path.name

            result = color_analyzer.analyze(crop)
            color_pcts = result.percentages
            overlay_img = color_analyzer.make_overlay(crop, result.masks)
            cv2.imwrite(str(overlay_path), overlay_img)
            overlay_name = overlay_path.name

            remark, severity = remark_engine.evaluate(color_pcts, kind=kind)

    json_path.write_text(json.dumps({
        "timestamp":  timestamp.isoformat(),
        "image_full": full_path.name,
        "image_crop": crop_name,
        "image_overlay": overlay_name,
        "image_cat": image_cat,
        "detections": detections,
        "crop_bbox":  crop_bbox,
        "colors":     color_pcts,
        "remark":     remark,
        "severity":   severity,
        "kind":       kind,
    }, indent=2))

    row_id = db.insert_detection(
        timestamp=timestamp.isoformat(),
        image_full=full_path.name,
        image_crop=crop_name,
        image_overlay=overlay_name,
        image_cat=image_cat,
        bbox=crop_bbox,
        color_pcts=color_pcts,
        remark=remark,
        severity=severity,
        model_version=POOP_MODEL_VERSION,
        kind=kind,
    )

    print(f"[{stamp}] Saved id={row_id} {full_path.name} severity={severity} colors={color_pcts}", flush=True)
    return row_id


def trigger_motor(dry_run: bool):
    """Run the dashboard-style full cleaning cycle in a background thread."""
    # New pattern for capture-triggered clean:
    # CCW (FULL_CYCLE_SECONDS) -> pause (FULL_CYCLE_PAUSE_S) ->
    # CW (FULL_CYCLE_SECONDS + FULL_CYCLE_CW_EXTRA_S) -> CCW2 (SHORT)
    def _run():
        try:
            # First CCW (original duration)
            gallon_rotate.rotate(
                direction=0,
                duration=FULL_CYCLE_SECONDS,
                delay=FULL_CYCLE_DELAY,
                simulate=dry_run,
            )
            # Pause
            time.sleep(FULL_CYCLE_PAUSE_S)
            # CW leg (add 1s)
            gallon_rotate.rotate(
                direction=1,
                duration=FULL_CYCLE_SECONDS + FULL_CYCLE_CW_EXTRA_S,
                delay=FULL_CYCLE_DELAY,
                simulate=dry_run,
            )
            # Short CCW2 final leg (1s)
            gallon_rotate.rotate(
                direction=0,
                duration=FULL_CYCLE_CCW2_S,
                delay=FULL_CYCLE_DELAY,
                simulate=dry_run,
            )
            print(f"[motor] full cleaning cycle done (simulate={dry_run})", flush=True)
        except Exception as exc:
            print(f"[motor] full cleaning cycle FAILED: {exc}", flush=True)

    threading.Thread(target=_run, daemon=True).start()


def capture_cat_image(frame, timestamp):
    """Persist one cat image that can be paired with the next poop event."""
    stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    cat_path = CAPTURE_DIR / f"capture_{stamp}_cat.jpg"
    cv2.imwrite(str(cat_path), frame)
    name = cat_path.name
    print(f"[capture] cat image saved: {name}", flush=True)
    return name


def inference_loop(cat_model, poop_model, shared, lock, stop_event, dry_run):
    while not stop_event.is_set():
        time.sleep(POLL_INTERVAL)

        with lock:
            frame = shared["frame"].copy() if shared["frame"] is not None else None
            state = shared["state"]
        if frame is None:
            continue

        timestamp = datetime.now()
        t = timestamp.strftime("%H:%M:%S")

        if state in ("MONITORING", "OCCUPIED"):
            results_raw = cat_model.predict(frame, imgsz=CAT_IMGSZ, conf=0.15,
                                            classes=[15], verbose=False)[0]
            top_conf = max((float(b.conf[0]) for b in results_raw.boxes), default=0.0)
            print(f"[{t}] Cat model top conf: {top_conf:.3f} (threshold {CAT_CONF})", flush=True)

            detections = []
            for box in results_raw.boxes:
                cls_name = cat_model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                if cls_name != CAT_CLASS or conf < CAT_CONF:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append({"class": cls_name, "confidence": round(conf, 4), "bbox": [x1, y1, x2, y2]})
            cat_detected = bool(detections)
            now_s = time.time()

            with lock:
                last_poop_scan = shared["last_poop_scan"]
                fallback_due = (time.time() - last_poop_scan) >= FALLBACK_POOP_INTERVAL

            if state == "MONITORING" and fallback_due:
                print(f"[{t}] Fallback poop scan (no cat trigger)", flush=True)
                with lock:
                    shared["state"] = "CHECKING"
            else:
                with lock:
                    if state == "MONITORING":
                        if cat_detected:
                            shared["state"] = "OCCUPIED"
                            shared["detections"] = detections
                            shared["cat_present_since"] = now_s
                            shared["cat_image_captured"] = False
                            print(f"[{t}] Cat entered — monitoring", flush=True)
                    elif state == "OCCUPIED":
                        if cat_detected:
                            shared["detections"] = detections
                            if shared.get("cat_present_since") is None:
                                shared["cat_present_since"] = now_s
                            should_capture_cat = (
                                not shared.get("cat_image_captured", False)
                                and (now_s - shared["cat_present_since"]) >= CAT_STAY_CAPTURE_S
                            )
                            if should_capture_cat:
                                cat_img_name = capture_cat_image(frame, timestamp)
                                shared["pending_cat_image"] = cat_img_name
                                shared["cat_image_captured"] = True
                                print(f"[{t}] Cat image captured: {cat_img_name}", flush=True)
                            print(f"[{t}] Cat still in box", flush=True)
                        else:
                            shared["detections"] = []
                            shared["state"] = "CHECKING"
                            shared["cat_present_since"] = None
                            print(f"[{t}] Cat left — scanning for poop", flush=True)

        elif state == "CHECKING":
            # Primary detection: run on full frame first with imgsz=640, conf=0.2
            results_full = poop_model.predict(frame, imgsz=POOP_IMGSZ, conf=POOP_CONF, verbose=False)[0]
            detections = []
            # Collect detections from full frame
            for box in results_full.boxes:
                cls_name = poop_model.names[int(box.cls[0])]
                if cls_name not in STOOL_CLASSES:
                    continue
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                detections.append({"class": cls_name, "confidence": round(conf, 4), "bbox": [x1, y1, x2, y2]})

            # Conditional fallback: only if full-frame produced no detections
            if not detections:
                h, w = frame.shape[:2]

                # A) Center crop covering ~55% of frame (between 50-60%)
                frac = 0.55
                crop_w = int(w * frac)
                crop_h = int(h * frac)
                cx = w // 2
                cy = h // 2
                cx1 = max(0, cx - crop_w // 2)
                cy1 = max(0, cy - crop_h // 2)
                cx2 = min(w, cx1 + crop_w)
                cy2 = min(h, cy1 + crop_h)
                center_crop = frame[cy1:cy2, cx1:cx2]

                # Run detection on center crop (lightweight single call)
                results_center = poop_model.predict(center_crop, imgsz=POOP_IMGSZ, conf=POOP_CONF, verbose=False)[0]
                for box in results_center.boxes:
                    cls_name = poop_model.names[int(box.cls[0])]
                    if cls_name not in STOOL_CLASSES:
                        continue
                    conf = float(box.conf[0])
                    bx1, by1, bx2, by2 = map(int, box.xyxy[0].tolist())
                    # Convert crop coords back to full-frame coordinates
                    fx1, fy1, fx2, fy2 = bx1 + cx1, by1 + cy1, bx2 + cx1, by2 + cy1
                    detections.append({"class": cls_name, "confidence": round(conf, 4), "bbox": [fx1, fy1, fx2, fy2]})

                # B) Secondary crop: fixed top-left region (~50% area)
                if not detections:
                    sx1, sy1 = 0, 0
                    sx2, sy2 = int(w * 0.5), int(h * 0.5)
                    sec_crop = frame[sy1:sy2, sx1:sx2]
                    results_sec = poop_model.predict(sec_crop, imgsz=POOP_IMGSZ, conf=POOP_CONF, verbose=False)[0]
                    for box in results_sec.boxes:
                        cls_name = poop_model.names[int(box.cls[0])]
                        if cls_name not in STOOL_CLASSES:
                            continue
                        conf = float(box.conf[0])
                        bx1, by1, bx2, by2 = map(int, box.xyxy[0].tolist())
                        # Convert secondary crop coords back to full-frame coordinates
                        fx1, fy1, fx2, fy2 = bx1 + sx1, by1 + sy1, bx2 + sx1, by2 + sy1
                        detections.append({"class": cls_name, "confidence": round(conf, 4), "bbox": [fx1, fy1, fx2, fy2]})

            # Persist results and update state (same as original behavior)
            with lock:
                shared["last_poop_scan"] = time.time()
                paired_cat_image = shared.get("pending_cat_image")
                print(f"[{t}] CHECKING done. paired_cat_image={paired_cat_image}, detections={len(detections)}", flush=True)
                if detections:
                    # Save detection using original full-frame coordinates
                    print(f"[{t}] Saving detection with image_cat={paired_cat_image}", flush=True)
                    save_detection(frame, timestamp, detections, image_cat=paired_cat_image)
                    shared["state"] = "DIRTY"
                    shared["detections"] = detections
                    shared["pending_cat_image"] = None
                    shared["cat_image_captured"] = False
                    print(f"[{t}] Poop detected — firing motor", flush=True)
                    trigger_motor(dry_run=dry_run)
                else:
                    shared["state"] = "MONITORING"
                    shared["detections"] = []
                    shared["pending_cat_image"] = None
                    shared["cat_image_captured"] = False
                    print(f"[{t}] No poop — back to idle", flush=True)

        elif state == "DIRTY":
            results = poop_model.predict(frame, imgsz=POOP_IMGSZ, conf=POOP_CONF, verbose=False)[0]
            poop_present = any(
                poop_model.names[int(b.cls[0])] in STOOL_CLASSES for b in results.boxes
            )
            with lock:
                if poop_present:
                    print(f"[{t}] Still dirty", flush=True)
                else:
                    shared["clean_since"] = time.time()
                    shared["state"] = "COOLDOWN"
                    shared["detections"] = []
                    print(f"[{t}] Box clean — cooldown {POST_CLEAN_COOLDOWN}s", flush=True)

        elif state == "COOLDOWN":
            with lock:
                if time.time() - shared["clean_since"] >= POST_CLEAN_COOLDOWN:
                    shared["state"] = "MONITORING"
                    print(f"[{t}] Re-armed", flush=True)

        gc.collect()


def parse_args():
    p = argparse.ArgumentParser(description="Catalyze detection + cleaning loop")
    p.add_argument("--dry-run", action="store_true",
                   help="Simulate motor calls instead of driving GPIO (safe on PC / no driver)")
    p.add_argument("--api-port", type=int, default=8000)
    p.add_argument("--no-api", action="store_true", help="Don't start the FastAPI server")
    return p.parse_args()


def main():
    args = parse_args()
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    db.init(DB_PATH)
    maint_thread, maint_stop   = maintenance.start(CAPTURE_DIR, DB_PATH)
    sync_thread,  sync_stop    = supabase_sync.start(CAPTURE_DIR)
    cmd_thread,   cmd_stop     = command_poller.start(dry_run=args.dry_run)

    try:
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(
            main={"size": (1280, 720), "format": "RGB888"},
            buffer_count=2,
        )
        picam2.configure(config)
        picam2.start()
        picam2.set_controls({"FrameDurationLimits": (100000, 100000)})  # 10 fps
        time.sleep(2)
    except Exception as exc:
        print(
            "Camera failed to start. Check that you are on a Raspberry Pi, "
            "the camera is connected/enabled, and picamera2/libcamera are installed.",
            file=sys.stderr,
            flush=True,
        )
        print(f"Camera error: {exc!r}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc

    print("Loading models...", flush=True)
    cat_model  = YOLO(CAT_WEIGHTS)
    poop_model = YOLO(POOP_WEIGHTS)
    print("Models ready.", flush=True)

    lock = threading.Lock()
    shared = {
        "frame":            None,
        "state":            "MONITORING",
        "detections":       [],
        "clean_since":      None,
        "last_poop_scan":   0.0,
        "cat_present_since":None,
        "cat_image_captured":False,
        "pending_cat_image":None,
    }
    stop_event = threading.Event()

    def frame_provider():
        with lock:
            f = shared["frame"]
            return f.copy() if f is not None else None

    push_thread, push_stop = live_frame_pusher.start(frame_provider)

    def _state_getter():
        with lock:
            return shared["state"]
    gpio_thread, gpio_stop = gpio_controller.start(_state_getter, dry_run=args.dry_run)

    if not args.no_api:
        def status_provider():
            with lock:
                return {
                    "state":          shared["state"],
                    "detections":     shared["detections"],
                    "last_poop_scan": shared["last_poop_scan"],
                }
        run_api(CAPTURE_DIR, status_provider, frame_provider=frame_provider, port=args.api_port)
        print(f"API listening on :{args.api_port}", flush=True)

    infer_thread = threading.Thread(
        target=inference_loop,
        args=(cat_model, poop_model, shared, lock, stop_event, args.dry_run),
        daemon=True,
    )
    infer_thread.start()

    cv2.namedWindow("Catalyze — Litter Monitor", cv2.WINDOW_NORMAL)
    print(f"Monitoring... dry_run={args.dry_run} (Q or Esc to stop)", flush=True)

    try:
        while True:
            frame = picam2.capture_array()

            with lock:
                shared["frame"] = frame.copy()
                state = shared["state"]
                detections = list(shared["detections"])
                clean_since = shared["clean_since"]

            cooldown_remaining = (
                max(0, int(POST_CLEAN_COOLDOWN - (time.time() - clean_since)))
                if state == "COOLDOWN" and clean_since else None
            )

            cv2.imshow("Catalyze — Litter Monitor",
                       draw_overlay(frame, state, detections, cooldown_remaining))
            if cv2.waitKey(200) & 0xFF in (ord("q"), 27):
                break

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        maint_stop.set()
        sync_stop.set()
        cmd_stop.set()
        push_stop.set()
        gpio_stop.set()
        infer_thread.join(timeout=15)
        maint_thread.join(timeout=5)
        sync_thread.join(timeout=5)
        cmd_thread.join(timeout=5)
        push_thread.join(timeout=5)
        gpio_thread.join(timeout=5)
        picam2.stop()
        cv2.destroyAllWindows()
        print("Stopped.", flush=True)


if __name__ == "__main__":
    main()
