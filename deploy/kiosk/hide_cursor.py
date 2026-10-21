#!/usr/bin/env python3
"""Hides the mouse pointer on the Pi's screen, by installing a cursor theme where every cursor is transparent.

labwc 0.7 can't hide the pointer itself, and unclutter only works on X11. The desktop (labwc) and the apps
(GTK / Chromium, which draw their own pointer over their windows) each get told to use it. Takes effect at the next login.
Undo: python3 deploy/kiosk/hide_cursor.py --undo
"""
import argparse
import re
import struct
import subprocess
from pathlib import Path

THEME = "blank"
THEME_DIR = Path.home() / ".local/share/icons" / THEME
LABWC_ENV = Path.home() / ".config/labwc/environment"
SETTING = f"XCURSOR_THEME={THEME}"
XSETTINGSD = Path.home() / ".config/xsettingsd/xsettingsd.conf"
NORMAL_THEME = "PiXflat"
# Every cursor name the system themes use, so no shape falls back to a visible one
SYSTEM_THEMES = [Path("/usr/share/icons/PiXflat/cursors"), Path("/usr/share/icons/Adwaita/cursors")]


def blank_xcursor(size=24):
    """An Xcursor file holding one fully transparent size x size image."""
    image_type = 0xFFFD0002
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1)
    toc = struct.pack("<III", image_type, size, 16 + 12)
    chunk = struct.pack("<IIIIIIIII", 36, image_type, size, 1, size, size, 0, 0, 0)
    return header + toc + chunk + bytes(4 * size * size)


def install():
    cursors = THEME_DIR / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    (THEME_DIR / "index.theme").write_text(f"[Icon Theme]\nName={THEME}\nComment=Invisible pointer for the dashboard kiosk\n")
    (cursors / "default").write_bytes(blank_xcursor())
    names = {p.name for d in SYSTEM_THEMES if d.is_dir() for p in d.iterdir()} - {"default"}
    for name in names:
        link = cursors / name
        if not link.exists():
            link.symlink_to("default")

    lines = [l for l in _env_lines() if not l.startswith("XCURSOR_THEME=")]
    _write_env(lines + [SETTING])
    _set_app_theme(THEME)
    print(f"Installed {len(names) + 1} invisible cursors in {THEME_DIR}; set {SETTING} in {LABWC_ENV}")


def undo():
    _write_env([l for l in _env_lines() if l != SETTING])
    _set_app_theme(NORMAL_THEME)
    print(f"Removed {SETTING} from {LABWC_ENV}; the normal pointer returns at the next login")


def _set_app_theme(name):
    subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", name], check=False)
    if XSETTINGSD.exists():
        text = re.sub(r'^Gtk/CursorThemeName .*$', f'Gtk/CursorThemeName "{name}"', XSETTINGSD.read_text(), flags=re.M)
        XSETTINGSD.write_text(text)


def _env_lines():
    return LABWC_ENV.read_text().splitlines() if LABWC_ENV.exists() else []


def _write_env(lines):
    LABWC_ENV.parent.mkdir(parents=True, exist_ok=True)
    LABWC_ENV.write_text("".join(l + "\n" for l in lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--undo", action="store_true", help="show the normal pointer again")
    undo() if parser.parse_args().undo else install()
