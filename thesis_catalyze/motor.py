"""
motor.py
Clean interface for triggering the drum cleaning cycle.

Wraps gallon_rotate so that the detection loop, command poller, and any
future callers share a single entry point for motor control.

Wiring (BCM numbering) — inherited from gallon_rotate.py:
  DIR+ : GPIO 17
  PUL+ : GPIO 27
"""
from __future__ import annotations

import threading
import time

import gallon_rotate

# ── Tunable constants ────────────────────────────────────────────────────
CLEAN_DIRECTION  = 1                       # 1 = CW, 0 = CCW
CLEAN_STEPS      = 2000                    # steps for one full drum rotation
CLEAN_STEP_DELAY = gallon_rotate.STEP_DELAY
FULL_CYCLE_SECONDS = 9.0                   # match dashboard full-cycle timing
FULL_CYCLE_PAUSE_S = 2.0                   # pause between CCW and CW legs


def run_cleaning_cycle(simulate: bool = False) -> None:
    """Block until one full cleaning rotation is complete.

    This function is synchronous/blocking — call it from a dedicated thread.
    Use trigger_cleaning_cycle_async() for fire-and-forget.
    """
    gallon_rotate.rotate(
        direction=CLEAN_DIRECTION,
        steps=CLEAN_STEPS,
        delay=CLEAN_STEP_DELAY,
        simulate=simulate,
    )


def run_full_cleaning_cycle(
    simulate: bool = False,
    duration: float = FULL_CYCLE_SECONDS,
    pause_s: float = FULL_CYCLE_PAUSE_S,
) -> None:
    """Run the dashboard-style full clean: CCW, pause, then CW."""
    # Match the dashboard's full-cycle pattern so both entry points behave the same.
    gallon_rotate.rotate(
        direction=0,
        duration=duration,
        delay=CLEAN_STEP_DELAY,
        simulate=simulate,
    )
    time.sleep(pause_s)
    gallon_rotate.rotate(
        direction=1,
        duration=duration,
        delay=CLEAN_STEP_DELAY,
        simulate=simulate,
    )


def trigger_cleaning_cycle_async(
    simulate: bool = False,
    on_done=None,
    on_error=None,
) -> threading.Thread:
    """Kick off a cleaning cycle in a daemon thread.

    on_done() and on_error(exc) are optional callbacks invoked after the
    cycle completes or fails.  Returns the Thread so callers can join it.
    """
    def _run():
        try:
            run_cleaning_cycle(simulate=simulate)
            print(f"[motor] cleaning cycle done (simulate={simulate})", flush=True)
            if on_done:
                on_done()
        except Exception as exc:
            print(f"[motor] cleaning cycle FAILED: {exc}", flush=True)
            if on_error:
                on_error(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def trigger_full_cleaning_cycle_async(
    simulate: bool = False,
    duration: float = FULL_CYCLE_SECONDS,
    pause_s: float = FULL_CYCLE_PAUSE_S,
    on_done=None,
    on_error=None,
) -> threading.Thread:
    """Kick off the dashboard-style full cycle in a daemon thread."""
    def _run():
        try:
            run_full_cleaning_cycle(simulate=simulate, duration=duration, pause_s=pause_s)
            print(f"[motor] full cleaning cycle done (simulate={simulate})", flush=True)
            if on_done:
                on_done()
        except Exception as exc:
            print(f"[motor] full cleaning cycle FAILED: {exc}", flush=True)
            if on_error:
                on_error(exc)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
