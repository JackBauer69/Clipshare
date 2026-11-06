# ClipShare

ClipShare is a small local network web app for sharing text and files between this computer and devices on the same trusted network. It is implemented with Python's standard library. Optional KDE Plasma integration provides a tray menu, systemd user services, and automatic stopping when the screen locks.

## What it does

- Serves a browser page on port `3570`, bound to all network interfaces (`0.0.0.0`).
- Shares up to 100 text messages, each at most 200 KB. Messages remain in memory and disappear when the server exits.
- Accepts files and folders in upload batches up to 3 GB. Uploaded data is stored in a private temporary directory and removed when the server exits.
- Displays the sender's LAN IP and supports individual file or ZIP downloads.
- Optionally runs as a systemd user service and offers a KDE tray controller and lock monitor.

The server uses plain HTTP and has no authentication. Run it only on a network you trust; anyone who can reach port 3570 can read shared content or upload files. The server does not configure a firewall.

## Project layout

```text
src/clipshare/clipboard_share.py  HTTP app
scripts/clipboard_share.py        direct source-checkout launcher
service/                           systemd templates and KDE integration
tests/                             HTTP behavior checks
docs/                              additional project notes
```

## Requirements

- Python 3.8 or newer. The web server itself uses only the Python standard library.
- For optional Plasma integration: KDE Plasma, a working systemd user session and D-Bus session, and Python modules `PySide6`, `dbus`, and `gi` available to `/usr/bin/python3`.

No packages are required to run the web app. The integration installer checks its optional desktop dependencies and reports when they are missing; it does not install packages or use `sudo`.

## Run manually

```bash
python3 ~/Projects/clipshare/scripts/clipboard_share.py
```

Open `http://localhost:3570` on this computer or `http://<PC-LAN-IP>:3570` on another device on the same network. Stop the server with Ctrl+C. There is no persistent configuration file; port, binding, and upload limits are constants near the top of `src/clipshare/clipboard_share.py`.

## KDE and systemd user integration

From a normal terminal inside the Plasma session:

```bash
~/Projects/clipshare/service/install.sh
```

The installer creates or updates the three user units under `~/.config/systemd/user/`, installs tray and lock-monitor helpers under `~/.local/lib/clipshare-integration/`, enables the two desktop helpers, and leaves the sharing service disabled until requested. It records backups of pre-existing unit files in the helper installation directory before replacing them.

The existing `~/.Scripts/Python/clipboard_share.py` path is a symlink to the project app, keeping already-installed units compatible. The installer replaces the old unit references with the project path on its next successful run.

Manage file sharing with:

```bash
systemctl --user start clipshare
systemctl --user stop clipshare
systemctl --user restart clipshare
systemctl --user status clipshare
```

To start sharing automatically at Plasma login, enable the app unit. Disable login startup with the second command:

```bash
systemctl --user enable clipshare
systemctl --user disable clipshare
```

The app unit belongs to `graphical-session.target`; logging out stops it. The lock monitor stops sharing on a screen-lock signal and does not restart it on unlock. The tray can also start, stop, restart, inspect, and show logs for the service. The app's stdout and stderr go to journald:

```bash
journalctl --user -u clipshare -n 100 --no-pager
journalctl --user -u clipshare -f
journalctl --user -u clipshare-tray -n 50 --no-pager
journalctl --user -u clipshare-lock-monitor -n 50 --no-pager
```

Remove the integration using:

```bash
~/Projects/clipshare/service/uninstall.sh
```

The uninstaller stops and disables the managed units and restores pre-installation unit backups when available. It preserves unit files whose contents changed after installation.

## Troubleshooting

- **Port already in use:** inspect the process bound to port 3570 (`ss -ltnp`) and stop that process or change `PORT` in the app.
- **Can't open it from another device:** confirm both devices are on a trusted reachable network and that local firewall rules allow TCP port 3570.
- **Unit changes do not appear:** run `systemctl --user daemon-reload`, then check `systemctl --user status clipshare` and the journal.
- **Tray or lock monitor fails:** check that the Plasma session and user D-Bus are available, then inspect their journal entries. Verify the optional Python modules with `/usr/bin/python3 -c 'import PySide6.QtWidgets, dbus.mainloop.glib; from gi.repository import GLib'`.
- **Uploads disappear:** this is expected. Uploaded files are temporary and are deleted when the server stops.

## Development and Git

Run the focused HTTP checks with:

```bash
cd ~/Projects/clipshare
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Check syntax with:

```bash
python3 -m compileall -q src service scripts tests
```

This repository is local-only. Review `git status` and `git diff` before committing changes; never add runtime data, caches, local credentials, or backup directories.
