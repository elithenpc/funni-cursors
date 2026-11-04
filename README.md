# funni-cursors

A small terminal-only multi-cursor utility for Linux X11.

## Controls

- **Ctrl + F1 ... F12**: spawn a cursor, or despawn it if it already exists.
- **Alt + F1 ... F12**: focus a cursor. The physical mouse is attached to that cursor's XInput master pointer.

The app does not create a GUI window. It prints status in the terminal.

## Requirements

- Linux running an **X11** session (not Wayland)
- \`xinput\`
- Python 3
- \`pynput\`

## Install (Linux Mint / Ubuntu)

Clone the repository, then run:

\`\`\`bash
chmod +x install.sh
./install.sh
\`\`\`

Run:

\`\`\`bash
funni-cursors
\`\`\`

Stop with Ctrl+C. Physical mouse devices are returned to their original master pointer on shutdown.

## Notes

Each spawned cursor is an independent XInput master pointer. Focusing a cursor moves the physical mouse device(s) from the core pointer to that cursor, so mouse movement and clicks are delivered to the focused cursor. This is pointer-device switching, not simultaneous independent mouse control. Multiple physical mice can be attached to the same focused cursor.

This first version targets X11. It will not work in a Wayland session.
