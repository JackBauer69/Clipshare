# Baseline implementation audit

This records the implementation found before the cross-platform redesign. The original `main` worktree remains available as an untouched reference.

- `src/clipshare/clipboard_share.py` contained the actual application: a standard-library `ThreadingHTTPServer`, inline browser UI, and a listener on `0.0.0.0:3570`.
- Text messages were held in memory, capped at 100 messages and 200 KB per message. Files and folders were uploaded in 8 MiB chunks, with a 3 GiB batch and total temporary-storage cap. Folder paths were retained and batches could be downloaded as ZIP files.
- Uploaded files lived in a temporary directory and were removed when the process exited. There was no authentication or TLS, so anyone able to reach the listener could access the content.
- The `service/` directory held systemd user units, a PySide6 KDE tray helper, a D-Bus/Plasma screen-lock monitor, and Linux-specific install/uninstall scripts. These are not part of the redesigned product and are removed from this branch.
- The source-checkout wrapper only located and ran the application module. The initial HTTP tests covered the page and text submission, but not uploads, limits, lifecycle, authentication, or packaging.

The replacement keeps the browser sharing interface and temporary data model, adds a Tkinter control window and session pairing, and moves packaging to native platform builds. The expanded test suite exercises HTTP behavior over loopback and temporary directories. See [the architecture plan](architecture-and-porting-plan.md) and [the development guide](development.md) for current decisions and remaining validation.
