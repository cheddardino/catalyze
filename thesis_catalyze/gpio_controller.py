"""
gpio_controller.py

Controls the three status LEDs and the manual-clean button.

BCM pin assignments:
  13  green  LED  — MONITORING / COOLDOWN (system idle / clean)
   6  yellow LED  — OCCUPIED / CHECKING   (cat detected / scanning)
   5  red    LED  — DIRTY                 (poop detected, motor running)
   0  input  button (active LOW, internal pull-up) — manual clean trigger

State → LED mapping:
  MONITORING  → green
  OCCUPIED    → yellow
  CHECKING    → yellow
  DIRTY       → red
  COOLDOWN    → green
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

try:
    import RPi.GPIO as GPIO
    _IS_RPI = True
except Exception:
    _IS_RPI = False

GREEN_PIN  = 13
YELLOW_PIN = 6
RED_PIN    = 5
BUTTON_PIN = 0

_LED_PINS = [GREEN_PIN, YELLOW_PIN, RED_PIN]

_STATE_LEDS: dict[str, tuple[bool, bool, bool]] = {
    "MONITORING": (True,  False, False),
    "OCCUPIED":   (False, True,  False),
    "CHECKING":   (False, True,  False),
    "DIRTY":      (False, False, True),
    "COOLDOWN":   (True,  False, False),
}

_DEBOUNCE_S        = 0.3   # button debounce
_STATUS_INTERVAL_S = 5.0   # how often to push device_status to Supabase
_POLL_S            = 0.1   # LED/button check loop interval


def _get_supabase():
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "")
        # Prefer service key for server-side operations to avoid RLS rejections
        key = (
            os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_KEY", "")
        )
        if url and key:
            return create_client(url, key)
    except Exception as exc:
        print(f"[gpio] Supabase init failed: {exc}", flush=True)
    return None


def _setup_gpio() -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in _LED_PINS:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def _set_leds(green: bool, yellow: bool, red: bool) -> None:
    GPIO.output(GREEN_PIN,  GPIO.HIGH if green  else GPIO.LOW)
    GPIO.output(YELLOW_PIN, GPIO.HIGH if yellow else GPIO.LOW)
    GPIO.output(RED_PIN,    GPIO.HIGH if red    else GPIO.LOW)


def _cleanup_gpio() -> None:
    _set_leds(False, False, False)
    for pin in _LED_PINS + [BUTTON_PIN]:
        try:
            GPIO.cleanup(pin)
        except Exception:
            pass


def _insert_clean_command(client) -> None:
    try:
        client.table("commands").insert({
            "type":         "clean",
            "status":       "pending",
            "triggered_by": "button",
        }).execute()
        print("[gpio] manual clean command inserted", flush=True)
    except Exception as exc:
        print(f"[gpio] failed to insert clean command: {exc}", flush=True)


def _push_device_status(client, state: str) -> None:
    try:
        client.table("device_status").upsert({
            "id":         1,
            "state":      state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass  # best-effort, don't spam logs


def _controller_loop(
    state_getter,
    stop_event: threading.Event,
    simulate: bool,
) -> None:
    client = _get_supabase()

    if not simulate and _IS_RPI:
        _setup_gpio()

    last_state       = None
    last_btn         = 1      # pull-up: idle = HIGH
    last_btn_time    = 0.0
    last_status_push = 0.0

    while not stop_event.is_set():
        state = state_getter()
        now   = time.time()

        # ── Update LEDs when state changes ──────────────────────────
        if state != last_state:
            last_state = state
            leds = _STATE_LEDS.get(state, (False, False, False))
            if not simulate and _IS_RPI:
                _set_leds(*leds)
            else:
                names = ["green", "yellow", "red"]
                active = [n for n, v in zip(names, leds) if v]
                print(f"[gpio][SIM] state={state} LEDs={active or ['off']}", flush=True)

        # ── Push device status to Supabase periodically ─────────────
        if client and now - last_status_push >= _STATUS_INTERVAL_S:
            threading.Thread(
                target=_push_device_status,
                args=(client, state),
                daemon=True,
            ).start()
            last_status_push = now

        # ── Check manual button (only on real Pi) ───────────────────
        if not simulate and _IS_RPI:
            btn = GPIO.input(BUTTON_PIN)
            if btn == GPIO.LOW and last_btn == GPIO.HIGH:  # falling edge
                if now - last_btn_time > _DEBOUNCE_S:
                    last_btn_time = now
                    print("[gpio] manual button pressed — queueing clean", flush=True)
                    if client:
                        threading.Thread(
                            target=_insert_clean_command,
                            args=(client,),
                            daemon=True,
                        ).start()
                    else:
                        # No network — trigger motor directly
                        import motor
                        motor.trigger_cleaning_cycle_async(simulate=simulate)
            last_btn = btn

        stop_event.wait(_POLL_S)

    if not simulate and _IS_RPI:
        _cleanup_gpio()

    # Mark offline in Supabase on clean shutdown
    if client:
        try:
            client.table("device_status").upsert({
                "id":         1,
                "state":      "OFFLINE",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass

    print("[gpio] controller stopped", flush=True)


def start(
    state_getter,
    dry_run: bool = False,
) -> tuple[threading.Thread, threading.Event]:
    """Start the GPIO controller in a background thread.

    state_getter: zero-arg callable returning the current state string.
    Returns (thread, stop_event).
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_controller_loop,
        args=(state_getter, stop_event, dry_run),
        daemon=True,
        name="gpio-controller",
    )
    thread.start()
    print(f"[gpio] controller started (simulate={dry_run})", flush=True)
    return thread, stop_event
