"""Standalone GPIO test for the manual button and three status LEDs.

Wiring uses BCM numbering:
- GPIO 13: green status LED
- GPIO 6: yellow status LED
- GPIO 5: red status LED
- GPIO 0: manual input button

Behavior:
- All three LEDs blink together continuously.
- Pressing the button prints "button pressed" in the terminal.
- The button does not control the LEDs.
"""

from __future__ import annotations

import time

try:
    from gpiozero import LED, Button
    from gpiozero import Device
    from gpiozero.pins.lgpio import LGPIOFactory
except Exception as exc:  # pragma: no cover - hardware-only script
    raise SystemExit(
        "gpiozero is not available. Run this script on the Raspberry Pi with gpiozero installed."
    ) from exc


GREEN_LED = 13
YELLOW_LED = 6
RED_LED = 5
BUTTON = 0

button_pressed = False


def button_callback() -> None:
    global button_pressed
    if not button_pressed:
        button_pressed = True
        print("button pressed", flush=True)


def main() -> None:
    pin_factory = LGPIOFactory()

    green = LED(GREEN_LED, pin_factory=pin_factory)
    yellow = LED(YELLOW_LED, pin_factory=pin_factory)
    red = LED(RED_LED, pin_factory=pin_factory)
    button = Button(BUTTON, pull_up=True, bounce_time=0.2, pin_factory=pin_factory)

    button.when_pressed = button_callback

    try:
        while True:
            green.on()
            yellow.on()
            red.on()
            time.sleep(0.5)

            green.off()
            yellow.off()
            red.off()
            time.sleep(0.5)

            if button_pressed and not button.is_pressed:
                button_pressed = False
    except KeyboardInterrupt:
        print("\nExiting program...", flush=True)
    finally:
        green.off()
        yellow.off()
        red.off()
        button.close()
        green.close()
        yellow.close()
        red.close()


if __name__ == "__main__":
    main()