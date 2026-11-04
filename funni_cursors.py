#!/usr/bin/env python3
"""Spawn and focus independent XInput master pointers on X11."""

from __future__ import annotations

import argparse
import re
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass

from Xlib import X, XK, display as xdisplay

APP_PREFIX = "Funni Cursor "
MAX_CURSORS = 12


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


class CursorManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.core_pointer_id: int | None = None
        self.original_attachments: dict[int, int] = {}
        self.active_slot: int | None = None
        self.refresh_devices()

    def refresh_devices(self) -> None:
        output = run_xinput("list", "--short")
        masters = re.findall(
            r"([^\n]+?)\s+id=(\d+)\s+\[master pointer \(\d+\)\]",
            output,
        )
        core = next((int(i) for name, i in masters if "Virtual core pointer" in name), None)
        if core is None:
            raise CommandError("Could not find the X11 Virtual core pointer.")
        self.core_pointer_id = core

        self.devices: dict[int, Device] = {}
        for line in output.splitlines():
            match = re.search(
                r"(.+?)\s+id=(\d+)\s+\[slave pointer \((\d+)\)\]",
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
        name = re.escape(f"{APP_PREFIX}{slot} pointer")
        match = re.search(name + r"\s+id=(\d+)\s+\[master pointer", output)
        return int(match.group(1)) if match else None

    def spawn(self, slot: int) -> None:
        with self.lock:
            if self.pointer_id(slot) is not None:
                print(f"Cursor {slot} already exists.")
                return
            run_xinput("create-master", f"{APP_PREFIX}{slot}", "false", "true")
            print(f"Spawned cursor {slot}.")

    def despawn(self, slot: int) -> None:
        with self.lock:
            pointer = self.pointer_id(slot)
            if pointer is None:
                print(f"Cursor {slot} does not exist.")
                return
            # Move any physical devices back to the core pointer before
            # destroying this master pair.
            self.refresh_devices()
            for device in self.devices.values():
                if device.attachment == pointer:
                    run_xinput("reattach", str(device.device_id), str(self.core_pointer_id))
            run_xinput("remove-master", str(pointer), "AttachToMaster", str(self.core_pointer_id))
            if self.active_slot == slot:
                self.active_slot = None
            print(f"Despawned cursor {slot}.")

    def focus(self, slot: int) -> None:
        with self.lock:
            pointer = self.pointer_id(slot)
            if pointer is None:
                print(f"Cursor {slot} does not exist. Press Ctrl+F{slot} first.")
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
                print("No physical slave pointer is attached to the core pointer.")
                return
            for device in candidates:
                self.original_attachments.setdefault(device.device_id, device.attachment)
                run_xinput("reattach", str(device.device_id), str(pointer))
            self.active_slot = slot
            print(f"Focused cursor {slot}. Physical mouse input now drives it.")

    def restore(self) -> None:
        with self.lock:
            for device_id, master_id in list(self.original_attachments.items()):
                try:
                    run_xinput("reattach", str(device_id), str(master_id))
                except CommandError:
                    pass
            self.original_attachments.clear()
            print("Restored physical mouse devices to their original masters.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Spawn and focus multiple independent X11 mouse cursors."
    )
    parser.add_argument("--max-cursors", type=int, default=MAX_CURSORS)
    args = parser.parse_args()

    if not sys.platform.startswith("linux") or not __import__("os").environ.get("DISPLAY"):
        print("This app requires an active X11 desktop session (DISPLAY).", file=sys.stderr)
        return 1
    if __import__("os").environ.get("XDG_SESSION_TYPE", "x11").lower() == "wayland":
        print("Wayland is not supported. Log into an X11 session.", file=sys.stderr)
        return 1
    if not shutil.which("xinput"):
        print("Missing xinput. Install it with: sudo apt install xinput", file=sys.stderr)
        return 1

    try:
        manager = CursorManager()
    except CommandError as exc:
        print(f"Could not initialise XInput: {exc}", file=sys.stderr)
        return 1

    max_cursors = max(1, min(args.max_cursors, 12))
    print("funni-cursors is running. Ctrl+F1..F12 spawn/despawn; Alt+F1..F12 focus.")
    print("Press Ctrl+C to stop and restore mouse devices.")

    def make_spawn(slot: int):
        return lambda: manager.despawn(slot) if manager.pointer_id(slot) is not None else manager.spawn(slot)

    def make_focus(slot: int):
        return lambda: manager.focus(slot)

    xdisplay_conn = xdisplay.Display()
    root = xdisplay_conn.screen().root
    grabbed: list[tuple[int, int]] = []

    try:
        for slot in range(1, max_cursors + 1):
            keycode = xdisplay_conn.keysym_to_keycode(
                XK.string_to_keysym(f"F{slot}")
            )
            for modifier in (X.ControlMask, X.Mod1Mask):
                # Also grab Caps Lock and Num Lock variants.
                for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                    root.grab_key(
                        keycode, modifier | extra, False,
                        X.GrabModeAsync, X.GrabModeAsync,
                    )
                    grabbed.append((keycode, modifier | extra))
        xdisplay_conn.sync()
        print("Hotkeys grabbed. They will not trigger desktop shortcuts.")

        def stop(_signum=None, _frame=None):
            manager.restore()
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        while True:
            event = xdisplay_conn.next_event()
            if event.type != X.KeyPress:
                continue
            modifiers = event.state & ~(X.LockMask | X.Mod2Mask)
            for slot in range(1, max_cursors + 1):
                keycode = xdisplay_conn.keysym_to_keycode(
                    XK.string_to_keysym(f"F{slot}")
                )
                if event.detail != keycode:
                    continue
                if modifiers == X.ControlMask:
                    if manager.pointer_id(slot) is not None:
                        manager.despawn(slot)
                    else:
                        manager.spawn(slot)
                elif modifiers == X.Mod1Mask:
                    manager.focus(slot)
                break
    except KeyboardInterrupt:
        pass
    finally:
        manager.restore()
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
