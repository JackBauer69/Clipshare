"""Exercise the real Tkinter control window under a display (for example Xvfb)."""

from pathlib import Path
import threading
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

from clipshare.desktop import ClipShareApp
from clipshare.instance import SingleInstanceLock


def root_exists(root):
    try:
        return bool(root.winfo_exists())
    except tk.TclError:
        return False


def pump_until(root, predicate, description, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not root_exists(root):
            break
        root.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {description}.")


def main():
    with tempfile.TemporaryDirectory(prefix="clipshare-gui-smoke-") as temporary:
        instance_lock = SingleInstanceLock(Path(temporary) / "instance.lock")
        if not instance_lock.acquire():
            raise AssertionError("Could not acquire the GUI smoke-test instance lock.")
        root = None
        app = None
        try:
            root = tk.Tk()
            with patch("clipshare.desktop.webbrowser.open", return_value=True):
                app = ClipShareApp(root, instance_lock)
                pump_until(root, lambda: app.session is not None, "initial server startup")
                first_session = app.session
                first_storage = Path(first_session.state.storage_root)
                assert root.title() == "ClipShare"
                assert root.winfo_viewable()
                assert app.status_var.get() == "Sharing is on"
                assert app.local_url_var.get().startswith("http://localhost:")
                assert app.code_var.get()
                assert app.stop_button.instate(["!disabled"])
                assert app.start_button.instate(["disabled"])

                app.stop_button.invoke()
                pump_until(root, lambda: app.session is None and not app.busy, "server shutdown")
                assert not first_storage.exists()
                assert app.status_var.get().startswith("Sharing is off")

                app.start_button.invoke()
                pump_until(root, lambda: app.session is not None, "server restart")
                second_session = app.session
                second_storage = Path(second_session.state.storage_root)
                with patch("clipshare.desktop.messagebox.askyesno", return_value=True):
                    app.quit_button.invoke()
                    pump_until(root, lambda: not root_exists(root), "Quit and window close")
                assert app.session is None
                assert not second_storage.exists()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and any(
                    thread.name in {"ClipShareHTTP", "ClipShareStop"}
                    for thread in threading.enumerate()
                ):
                    time.sleep(0.01)
                assert not any(
                    thread.name in {"ClipShareHTTP", "ClipShareStop"}
                    for thread in threading.enumerate()
                )
        finally:
            try:
                if app is not None and app.session is not None:
                    app.session.stop()
            finally:
                try:
                    if root is not None and root_exists(root):
                        root.destroy()
                finally:
                    instance_lock.write_state({"running": False})
                    instance_lock.release()
        assert instance_lock.file is None
    print("Tkinter GUI startup, controls, restart, cleanup, and quit passed")


if __name__ == "__main__":
    main()
