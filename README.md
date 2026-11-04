# funni-cursors

A terminal-controlled multi-cursor utility for Linux X11.

## Controls

To avoid Linux virtual-terminal switching shortcuts, the app uses the **number row** with Shift:

- **Ctrl + Shift + 1 ... 9, 0**: spawn a numbered cursor, or despawn it if it already exists. The keys map to cursors 1 through 10, with 0 controlling cursor 10.
- **Alt + Shift + 1 ... 9, 0**: focus the matching cursor and route physical mouse input to it.

The app does not register Ctrl + Alt shortcuts. Avoid Ctrl + Alt + F1 ... F6 because Linux uses those to switch to a virtual terminal.

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
