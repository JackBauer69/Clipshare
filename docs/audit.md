# Initial implementation audit

- `src/clipshare/clipboard_share.py` is the original executable web app. It has no third-party imports and uses `ThreadingHTTPServer` on `0.0.0.0:3570`.
- Text sharing is in-memory, capped at 100 entries and 200 KB per message. Uploads are chunked, limited to 3 GB per batch and in temporary storage, and removed at process shutdown.
- The web app has no authentication or TLS. Anyone with network access to its port can read and add content.
- `service/install.py` provisions three systemd **user** units. The share unit is not enabled by default; the tray and lock monitor are enabled for the Plasma graphical session. The monitor stops sharing on screen lock.
- The tray integration imports PySide6; the lock monitor imports dbus-python and PyGObject. These are external to the web app.
- The existing installed units and helpers pointed to the old `~/.Scripts` paths. The old application entry is now a symlink to `src/clipshare/clipboard_share.py`, so existing service references continue to resolve. Running this project's installer regenerates the units with the new project path.
- The user-scope systemd bus could not be reached from the migration environment. Active/enabled status and a live service restart therefore remain unverified. The optional desktop modules import successfully under `/usr/bin/python3`, which is the interpreter used by the service templates. The interactive Plasma integration still could not be exercised in this session.
