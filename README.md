# funni-cursors

A terminal-controlled multi-cursor utility for Linux X11.

## Controls

To avoid Linux virtual-terminal switching shortcuts, the app uses **Shift-modified function keys**:

- **Ctrl + Shift + F1 ... F12**: spawn a numbered cursor, or despawn it if it already exists.
- **Alt + Shift + F1 ... F12**: focus a cursor and route physical mouse input to it.

Do not use Ctrl + Alt + F1 ... F6: those combinations can switch away from the desktop to a Linux virtual terminal.

## Cursor appearance

Each spawned XInput master pointer receives its own cursor image with a coloured number badge. The cursor remains visible while another cursor is focused, at the last position where it was left. The app does not open a control-panel window; the numbered cursor artwork is rendered by the X server.

## Requirements

- Linux running an **X11** session (not Wayland)
- Python 3, python-xlib, Pillow
- `xinput` and `xcursorgen`
- Xcursor and Xi runtime libraries

## Install (Linux Mint / Ubuntu)

Clone the repository, then run:

```bash
chmod +x install.sh
./install.sh
```

The installer deliberately does not run `apt update`, so unrelated broken third-party APT repositories do not block installation.

Run:

```bash
funni-cursors
```

Stop with Ctrl+C. Physical mouse devices are returned to their original master pointer, and cursors created by that run are removed.

## Current limitation

Each cursor is a separate XInput master pointer and stays visible, but this version still switches the physical mouse between them. It does not yet provide simultaneous independent movement from one mouse. Separate physical mice can be attached to different master pointers manually.

This project targets X11 and will not work in a Wayland session.
