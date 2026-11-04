#!/usr/bin/env python3
"""Spawn numbered, persistent XInput master pointers on an X11 desktop."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from Xlib import X, XK, display as xdisplay

APP_PREFIX = "Funni Cursor "
MAX_CURSORS = 12
PALETTE = [
    "#2878E8", "#E28A22", "#22A06B", "#B45AC8",
    "#D64B55", "#159DA8", "#8A6DDB", "#A56A43",
    "#D05C9B", "#688A35", "#5266C9", "#B18A22",
]


class CommandError(RuntimeError):
    pass


def run_xinput(*args: str) -> str:
    result = subprocess.run(
        ["xinput", *args], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise CommandError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


@dataclass
class Device:
    device_id: int
    attachment: int
    name: str


class NumberedCursorImages:
    """Create a numbered Xcursor image and assign it to one master pointer."""

    def __init__(self) -> None:
        self.cache = Path.home() / ".cache" / "funni-cursors"
        self.cache.mkdir(parents=True, exist_ok=True)
        if not shutil.which("xcursorgen"):
            raise CommandError("Missing xcursorgen. Install package: xcursorgen")

        x11_name = ctypes.util.find_library("X11")
        xi_name = ctypes.util.find_library("Xi")
        xc_name = ctypes.util.find_library("Xcursor")
        if not all((x11_name, xi_name, xc_name)):
            raise CommandError("Missing X11 cursor libraries. Install libxi6 and libxcursor1.")

        self.x11 = ctypes.CDLL(x11_name)
        self.xi = ctypes.CDLL(xi_name)
        self.xcursor = ctypes.CDLL(xc_name)

        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

        self.xcursor.XcursorFilenameLoadCursor.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p
        ]
        self.xcursor.XcursorFilenameLoadCursor.restype = ctypes.c_ulong

        self.xi.XIDefineCursor.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong
        ]
        self.xi.XIDefineCursor.restype = ctypes.c_int

        self.xdisplay = self.x11.XOpenDisplay(None)
        if not self.xdisplay:
            raise CommandError("Could not open the X11 display for cursor artwork.")
        self.root = self.x11.XDefaultRootWindow(self.xdisplay)
        self.handles: dict[int, int] = {}

    def _build(self, slot: int) -> Path:
        image_path = self.cache / f"cursor-{slot}.png"
        config_path = self.cache / f"cursor-{slot}.conf"
        cursor_path = self.cache / f"cursor-{slot}.cursor"

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # A familiar pointer arrow with a numbered colour badge.
        arrow = [(3, 2), (3, 43), (14, 32), (23, 51), (31, 47), (22, 29), (39, 28)]
        draw.polygon(arrow, fill="white", outline="#111111", width=3)
        draw.ellipse((27, 2, 62, 37), fill=PALETTE[(slot - 1) % len(PALETTE)],
                     outline="white", width=3)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20
            )
        except OSError:
            font = ImageFont.load_default()
        label = str(slot)
        bounds = draw.textbbox((0, 0), label, font=font, stroke_width=0)
        text_w, text_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        draw.text(
            (44.5 - text_w / 2, 19.5 - text_h / 2 - bounds[1]),
            label, font=font, fill="white",
        )
        image.save(image_path)
        config_path.write_text(f"64 3 3 {image_path} 0\n", encoding="utf-8")

        result = subprocess.run(
            ["xcursorgen", str(config_path), str(cursor_path)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode:
            raise CommandError(result.stderr.strip() or "xcursorgen could not build a cursor.")
        return cursor_path

    def apply(self, slot: int, pointer_id: int) -> None:
        cursor_path = self._build(slot)
        cursor = self.xcursor.XcursorFilenameLoadCursor(
            self.xdisplay, os.fsencode(cursor_path)
        )
        if not cursor:
            raise CommandError(f"Could not load the numbered cursor image for cursor {slot}.")
        ok = self.xi.XIDefineCursor(
            self.xdisplay, pointer_id, self.root, cursor
        )
        if not ok:
            raise CommandError(f"Could not assign the numbered image to cursor {slot}.")
        self.handles[slot] = cursor
        self.x11.XFlush(self.xdisplay)

    def close(self) -> None:
        if self.xdisplay:
            self.x11.XCloseDisplay(self.xdisplay)
            self.xdisplay = None


class CursorManager:
    def __init__(self, renderer: NumberedCursorImages) -> None:
        self.lock = threading.RLock()
        self.renderer = renderer
        self.core_pointer_id: int | None = None
        self.original_attachments: dict[int, int] = {}
        self.active_slot: int | None = None
        self.refresh_devices()

    def refresh_devices(self) -> None:
        output = run_xinput("list", "--short")
        core = None
        for line in output.splitlines():
            if "Virtual core pointer" in line and "[master pointer" in line:
                match = re.search(r"\bid=(\d+)", line)
                if match:
                    core = int(match.group(1))
                    break
        if core is None:
            raise CommandError("Could not find the X11 Virtual core pointer.")
        self.core_pointer_id = core

        self.devices: dict[int, Device] = {}
        for line in output.splitlines():
            match = re.search(
                r"(.+?)\s+id=(\d+)\s+\[slave pointer\s+\((\d+)\)\]",
                line,
            )
            if not match:
                continue
            name, device_id, attachment = match.groups()
            name = name.strip().lstrip("↳").strip()
            device_id, attachment = int(device_id), int(attachment)
            if "XTEST" in name.upper() or name.startswith("Virtual"):
                continue
            self.devices[device_id] = Device(device_id, attachment, name)

    def pointer_id(self, slot: int) -> int | None:
        output = run_xinput("list", "--short")
        pattern = re.escape(f"{APP_PREFIX}{slot} pointer") + r"\s+id=(\d+)\s+\[master pointer"
        match = re.search(pattern, output)
        return int(match.group(1)) if match else None

    def spawn(self, slot: int) -> None:
        with self.lock:
            existing_pointer = self.pointer_id(slot)
            if existing_pointer is not None:
                self.renderer.apply(slot, existing_pointer)
                print(f"Cursor {slot} already exists; refreshed its numbered appearance.")
                return
            run_xinput("create-master", f"{APP_PREFIX}{slot}", "false", "true")
            pointer = self.pointer_id(slot)
            if pointer is None:
                raise CommandError(f"XInput created cursor {slot}, but its pointer ID was not found.")
            try:
                self.renderer.apply(slot, pointer)
            except Exception:
                run_xinput("remove-master", str(pointer), "AttachToMaster", str(self.core_pointer_id))
                raise
            print(f"Spawned numbered cursor {slot}. It remains visible while inactive.")

    def despawn(self, slot: int, quiet: bool = False) -> None:
        with self.lock:
            pointer = self.pointer_id(slot)
            if pointer is None:
                if not quiet:
                    print(f"Cursor {slot} does not exist.")
                return
            self.refresh_devices()
            for device in self.devices.values():
                if device.attachment == pointer:
                    run_xinput("reattach", str(device.device_id), str(self.core_pointer_id))
            run_xinput("remove-master", str(pointer), "AttachToMaster", str(self.core_pointer_id))
            if self.active_slot == slot:
                self.active_slot = None
            if not quiet:
                print(f"Despawned cursor {slot}.")

    def focus(self, slot: int) -> None:
        with self.lock:
            pointer = self.pointer_id(slot)
            if pointer is None:
                print(f"Cursor {slot} does not exist. Spawn it with Ctrl+Shift+F{slot}.")
                return
            self.refresh_devices()
            previous_pointer = (
                self.pointer_id(self.active_slot) if self.active_slot is not None else None
            )
            candidates = [
                device for device in self.devices.values()
                if device.attachment == self.core_pointer_id
                or (previous_pointer is not None and device.attachment == previous_pointer)
            ]
            if not candidates:
                print("No physical mouse device is available to focus.")
                return
            for device in candidates:
                self.original_attachments.setdefault(device.device_id, device.attachment)
                run_xinput("reattach", str(device.device_id), str(pointer))
            self.active_slot = slot
            print(f"Focused cursor {slot}. Your physical mouse now controls it.")

    def cleanup(self) -> None:
        with self.lock:
            self.restore()
            for slot in range(1, MAX_CURSORS + 1):
                try:
                    self.despawn(slot, quiet=True)
                except CommandError as exc:
                    print(f"Cleanup warning for cursor {slot}: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Spawn numbered, persistent X11 mouse cursors."
    )
    parser.add_argument("--max-cursors", type=int, default=MAX_CURSORS)
    args = parser.parse_args()
    max_cursors = max(1, min(args.max_cursors, MAX_CURSORS))

    if not sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
        print("This app requires an active X11 desktop session (DISPLAY).", file=sys.stderr)
        return 1
    if os.environ.get("XDG_SESSION_TYPE", "x11").lower() == "wayland":
        print("Wayland is not supported. Log into an X11 session.", file=sys.stderr)
        return 1
    if not shutil.which("xinput"):
        print("Missing xinput. Install it with: sudo apt install xinput", file=sys.stderr)
        return 1
    if not shutil.which("xcursorgen"):
        print("Missing xcursorgen. Install it with: sudo apt install xcursorgen", file=sys.stderr)
        return 1

    renderer = None
    manager = None
    try:
        renderer = NumberedCursorImages()
        manager = CursorManager(renderer)
    except (CommandError, OSError) as exc:
        if renderer:
            renderer.close()
        print(f"Could not initialise funni-cursors: {exc}", file=sys.stderr)
        return 1

    print("funni-cursors is running.")
    print("Ctrl+Shift+F1..F12: spawn/despawn numbered cursors.")
    print("Alt+Shift+F1..F12: focus a cursor.")
    print("Ctrl+Alt+F is deliberately NOT used, so it cannot trigger a VT switch.")
    print("Press Ctrl+C to restore devices and remove cursors created by this run.")

    xdisplay_conn = xdisplay.Display()
    root = xdisplay_conn.screen().root
    grabbed: list[tuple[int, int]] = []
    modifiers_by_slot: dict[int, tuple[int, int]] = {}

    try:
        for slot in range(1, max_cursors + 1):
            keycode = xdisplay_conn.keysym_to_keycode(XK.string_to_keysym(f"F{slot}"))
            modifiers_by_slot[slot] = (
                X.ControlMask | X.ShiftMask,
                X.Mod1Mask | X.ShiftMask,
            )
            for modifier in modifiers_by_slot[slot]:
                for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                    root.grab_key(
                        keycode, modifier | extra, False,
                        X.GrabModeAsync, X.GrabModeAsync,
                    )
                    grabbed.append((keycode, modifier | extra))
        xdisplay_conn.sync()
        print("Hotkeys grabbed. No Ctrl+Alt+F key combinations are registered.")

        def stop(_signum=None, _frame=None):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        while True:
            event = xdisplay_conn.next_event()
            if event.type != X.KeyPress:
                continue
            modifiers = event.state & ~(X.LockMask | X.Mod2Mask)
            for slot in range(1, max_cursors + 1):
                keycode = xdisplay_conn.keysym_to_keycode(XK.string_to_keysym(f"F{slot}"))
                if event.detail != keycode:
                    continue
                spawn_mod, focus_mod = modifiers_by_slot[slot]
                if modifiers == spawn_mod:
                    if manager.pointer_id(slot) is not None:
                        manager.despawn(slot)
                    else:
                        manager.spawn(slot)
                elif modifiers == focus_mod:
                    manager.focus(slot)
                break
    except KeyboardInterrupt:
        print("\nStopping funni-cursors...")
    finally:
        manager.cleanup()
        renderer.close()
        for keycode, modifiers in grabbed:
            try:
                root.ungrab_key(keycode, modifiers)
            except Exception:
                pass
        xdisplay_conn.sync()
        xdisplay_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
