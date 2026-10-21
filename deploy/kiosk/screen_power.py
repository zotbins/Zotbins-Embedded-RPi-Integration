#!/usr/bin/env python3
"""Turns the dashboard screen off when the bin hasn't been used for a while, and back on when it is.

Activity is the lid being open (IR beam clear) or any keyboard / mouse / touch input.
Started at desktop login by zotbins-screen-power.desktop; it needs the desktop session for wlr-randr.
The IR pin is read with pinctrl, which only reads it, so it doesn't interfere with the pipeline.
"""
import argparse
import glob
import os
import select
import subprocess
import time

POLL_S = 0.25
RESCAN_S = 5.0  # How often to look for newly plugged-in input devices


def lid_open(pin, open_level):
    out = subprocess.run(["pinctrl", "get", str(pin)], capture_output=True, text=True).stdout
    return f"| {open_level}" in out


def open_new_inputs(fds):
    for path in glob.glob("/dev/input/event*"):
        if path in fds.values():
            continue
        try:
            with open(f"/sys/class/input/{os.path.basename(path)}/device/name") as f:
                if "Jack" in f.read():  # HDMI/audio plug events, not a person
                    continue
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        fds[fd] = path


def input_activity(fds):
    if not fds:
        time.sleep(POLL_S)
        return False
    ready, _, _ = select.select(list(fds), [], [], POLL_S)
    for fd in ready:
        try:
            while os.read(fd, 4096):
                pass
        except BlockingIOError:
            pass
        except OSError:  # Device unplugged
            os.close(fd)
            del fds[fd]
    return bool(ready)


def set_screen(output, on):
    subprocess.run(["wlr-randr", "--output", output, "--on" if on else "--off"], check=False)
    if on:
        # With the output off the browser loses full-screen, and labwc 0.7 can't use DPMS instead
        # (wlopm fails). Closing the browser makes zotbins-kiosk reopen it full-screen.
        subprocess.run(["pkill", "-x", "chromium-browse"], check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--timeout", type=float, default=300, help="seconds without activity before the screen turns off")
    parser.add_argument("--pin", type=int, default=5, help="IR sensor GPIO (config.py ir_gpio_pin)")
    parser.add_argument("--open-level", choices=["hi", "lo"], default="hi", help="pin level while the lid is open")
    parser.add_argument("--output", default="HDMI-A-1", help="display to switch (wlr-randr lists them)")
    args = parser.parse_args()

    fds = {}
    last_activity = last_rescan = time.monotonic()
    screen_on = True

    while True:
        now = time.monotonic()
        if now - last_rescan > RESCAN_S:
            open_new_inputs(fds)
            last_rescan = now
        if input_activity(fds) or lid_open(args.pin, args.open_level):
            last_activity = time.monotonic()
            if not screen_on:
                set_screen(args.output, True)
                screen_on = True
        elif screen_on and time.monotonic() - last_activity > args.timeout:
            set_screen(args.output, False)
            screen_on = False


if __name__ == "__main__":
    main()
