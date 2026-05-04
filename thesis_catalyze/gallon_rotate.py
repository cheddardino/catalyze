"""
gallon_rotate.py

Simple Raspberry Pi stepper motor controller for "rotating the gallon".

Wiring (BCM numbering):
- DIR+ : GPIO 17
- PUL+ : GPIO 27
- GND  : physical pin 9 (connect to Pi GND)

Usage (on the Pi):
  python3 gallon_rotate.py cw --duration 0.8
  python3 gallon_rotate.py ccw --steps 2000

This script drives the DIR and PUL pins directly. Adjust `STEP_DELAY`
to change speed. Use `--simulate` to run without RPi.GPIO installed.
"""

import time
import argparse
import sys
import threading

try:
    import RPi.GPIO as GPIO
    IS_RPI = True
except Exception:
    IS_RPI = False

# BCM pins
DIR_PIN = 17  # DIR+
PUL_PIN = 27  # PUL+

# default half-pulse delay (seconds). A full step cycle = 2 * STEP_DELAY
STEP_DELAY = 0.001

_GPIO_LOCK = threading.Lock()


def _ensure_gpio_ready(simulate=False):
    if simulate or not IS_RPI:
        return
    # setmode may already be called by gpio_controller; only call if not set
    if GPIO.getmode() is None:
        GPIO.setmode(GPIO.BCM)
    # Always ensure our pins are set up as outputs (safe to call multiple times)
    try:
        GPIO.setup(DIR_PIN, GPIO.OUT)
        GPIO.setup(PUL_PIN, GPIO.OUT)
    except RuntimeError:
        # Pins may already be set up; that's fine
        pass
    # Reset to LOW state
    GPIO.output(DIR_PIN, GPIO.LOW)
    GPIO.output(PUL_PIN, GPIO.LOW)


def init_gpio(simulate=False):
    if simulate or not IS_RPI:
        print("[SIM] init GPIO (DIR={}, PUL={})".format(DIR_PIN, PUL_PIN))
        return
    _ensure_gpio_ready(simulate=simulate)


def cleanup_gpio(simulate=False):
    if simulate or not IS_RPI:
        print("[SIM] cleanup GPIO")
        return
    try:
        # Reset motor pins to LOW (do NOT call GPIO.cleanup() as it affects all pins)
        GPIO.output(PUL_PIN, GPIO.LOW)
        GPIO.output(DIR_PIN, GPIO.LOW)
    except RuntimeError:
        # GPIO mode may already be reset by another caller.
        pass


def step_pulses(direction: int, steps: int, delay: float = STEP_DELAY, simulate=False):
    """Run `steps` step pulses. direction: 1 => CW (DIR HIGH), 0 => CCW (DIR LOW)."""
    if simulate or not IS_RPI:
        dir_str = 'CW' if direction else 'CCW'
        print(f"[SIM] step_pulses: dir={dir_str}, steps={steps}, delay={delay}")
        for i in range(steps):
            if i % 500 == 0:
                print(f"[SIM] pulse {i+1}/{steps}")
        return

    _ensure_gpio_ready(simulate=simulate)
    GPIO.output(DIR_PIN, GPIO.HIGH if direction else GPIO.LOW)
    # small settle
    time.sleep(0.01)
    for i in range(steps):
        GPIO.output(PUL_PIN, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(PUL_PIN, GPIO.LOW)
        time.sleep(delay)
        # intermittent small delay or logging could be added here


def rotate(direction: int, steps: int = None, duration: float = None, delay: float = STEP_DELAY, simulate=False):
    """Rotate the motor.

    Provide either `steps` or `duration` (seconds). If both provided, `steps` is used.
    direction: 1 => CW, 0 => CCW
    """
    if steps is None:
        if duration is None:
            steps = 2000
        else:
            # each full cycle uses 2 * delay seconds
            steps = max(1, int(duration / (delay * 2)))

    print(f"Rotate: direction={'CW' if direction==1 else 'CCW'}, steps={steps}, delay={delay}")
    with _GPIO_LOCK:
        init_gpio(simulate=simulate)
        try:
            step_pulses(direction, steps, delay=delay, simulate=simulate)
        finally:
            cleanup_gpio(simulate=simulate)


def main(argv=None):
    p = argparse.ArgumentParser(description='Rotate the gallon stepper on Raspberry Pi')
    p.add_argument('action', choices=['cw', 'ccw'], help='Direction')
    p.add_argument('--steps', '-s', type=int, help='Number of steps to run')
    p.add_argument('--duration', '-d', type=float, help='Duration in seconds (alternative to steps)')
    p.add_argument('--delay', type=float, default=STEP_DELAY, help='Half-pulse delay in seconds')
    p.add_argument('--simulate', action='store_true', help='Run without accessing RPi.GPIO')
    args = p.parse_args(argv)

    direction = 1 if args.action == 'cw' else 0
    rotate(direction, steps=args.steps, duration=args.duration, delay=args.delay, simulate=args.simulate)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Interrupted by user')
        cleanup_gpio()
