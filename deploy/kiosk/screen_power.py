#!/usr/bin/env python3
"""Turns the dashboard screen off when the bin hasn't been used for a while, and back on when it is.

Activity is the lid being open (IR beam clear) or any keyboard / mouse / touch input.
Started at desktop login by zotbins-screen-power.desktop; it needs the desktop session for wlr-randr.
The IR pin is read with pinctrl, which only reads it, so it doesn't interfere with the pipeline.

It also parks the mouse pointer in the top-left corner, at login and once the mouse has been left alone,
using a virtual mouse (/dev/uinput; deploy/kiosk/99-zotbins-uinput.rules gives the input group access).
"""
import argparse
import fcntl
import glob
import logging
import os
import select
import struct
import subprocess
import time

log = logging.getLogger("ScreenPower")

POLL_S = 0.25
RESCAN_S = 5.0  # How often to look for newly plugged-in input devices
PARKER_NAME = "zotbins-pointer-park"  # Our own virtual mouse; its moves aren't activity


class PointerParker:
    """A virtual mouse that only ever moves up and left, so the pointer ends up in the top-left corner."""
    EV_SYN, EV_KEY, EV_REL, REL_X, REL_Y, BTN_LEFT = 0, 1, 2, 0, 1, 0x110
    UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT, UI_DEV_CREATE = 0x40045564, 0x40045565, 0x40045566, 0x5501

    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        for evbit in (self.EV_KEY, self.EV_REL):
            fcntl.ioctl(self.fd, self.UI_SET_EVBIT, evbit)
        fcntl.ioctl(self.fd, self.UI_SET_KEYBIT, self.BTN_LEFT)  # without a button it isn't treated as a mouse
        for relbit in (self.REL_X, self.REL_Y):
            fcntl.ioctl(self.fd, self.UI_SET_RELBIT, relbit)
        # struct uinput_user_dev: name, bus/vendor/product/version, ff_effects_max, then 4 x 64 abs ints
        os.write(self.fd, struct.pack("80sHHHHI", PARKER_NAME.encode(), 0x03, 1, 1, 1, 0) + bytes(4 * 64 * 4))
        fcntl.ioctl(self.fd, self.UI_DEV_CREATE)

    def park(self):
        for _ in range(10):  # the pointer stops at the screen edge, so overshooting is fine
            self._event(self.EV_REL, self.REL_X, -500)
            self._event(self.EV_REL, self.REL_Y, -500)
            self._event(self.EV_SYN, 0, 0)

    def _event(self, type_, code, value):
        os.write(self.fd, struct.pack("llHHi", 0, 0, type_, code, value))  # struct input_event


def make_parker():
    try:
        return PointerParker()
    except OSError as e:
        log.warning("Can't park the pointer (%s); install deploy/kiosk/99-zotbins-uinput.rules", e)
        return None


def lid_open(pin, open_level):
    out = subprocess.run(["pinctrl", "get", str(pin)], capture_output=True, text=True).stdout
    return f"| {open_level}" in out


def open_new_inputs(fds):
    for path in glob.glob("/dev/input/event*"):
        if path in fds.values():
            continue
        try:
            with open(f"/sys/class/input/{os.path.basename(path)}/device/name") as f:
                name = f.read().strip()
            if "Jack" in name or name == PARKER_NAME:  # HDMI/audio plug events and our own moves, not a person
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
    parser.add_argument("--park-after", type=float, default=10, help="seconds after the last input before the pointer goes top-left")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

    parker = make_parker()
    fds = {}
    last_activity = last_rescan = last_input = time.monotonic()
    screen_on = True
    parked = False

    while True:
        now = time.monotonic()
        if now - last_rescan > RESCAN_S:
            open_new_inputs(fds)
            last_rescan = now
        used = input_activity(fds)
        if used:
            last_input, parked = time.monotonic(), False
        elif parker and not parked and time.monotonic() - last_input > args.park_after:
            parker.park()  # also at login: last_input starts at startup
            parked = True
        if used or lid_open(args.pin, args.open_level):
            last_activity = time.monotonic()
            if not screen_on:
                set_screen(args.output, True)
                screen_on = True
        elif screen_on and time.monotonic() - last_activity > args.timeout:
            set_screen(args.output, False)
            screen_on = False


if __name__ == "__main__":
    main()
