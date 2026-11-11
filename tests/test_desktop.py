import queue
import unittest
from unittest.mock import patch

try:
    from clipshare.desktop import ClipShareApp
except ModuleNotFoundError as error:
    if error.name not in {"tkinter", "_tkinter"}:
        raise
    ClipShareApp = None


class FakeRoot:
    def __init__(self):
        self.alive = True
        self.callbacks = []

    def after(self, delay, callback):
        self.callbacks.append((delay, callback))

    def winfo_exists(self):
        return self.alive

    def destroy(self):
        self.alive = False


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeButton:
    def __init__(self):
        self.state = None

    def configure(self, **values):
        self.state = values.get("state", self.state)


class FakeLock:
    def __init__(self):
        self.states = []

    def write_state(self, state):
        self.states.append(dict(state))


class FailingThenSuccessfulSession:
    def __init__(self):
        self.calls = 0

    def stop(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("simulated shutdown failure")


@unittest.skipIf(ClipShareApp is None, "Tkinter is not installed for this Python interpreter")
class DesktopShutdownTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(ClipShareApp)
        app.root = FakeRoot()
        app.instance_lock = FakeLock()
        app.session = FailingThenSuccessfulSession()
        app.events = queue.Queue()
        app.busy = False
        app.quit_after_stop = False
        app.status_var = FakeVariable("Sharing is on")
        app.port_notice_var = FakeVariable()
        app.local_url_var = FakeVariable("http://localhost:3570/")
        app.lan_url_var = FakeVariable("http://192.0.2.10:3570/")
        app.code_var = FakeVariable("ABCD-EFGH-JKLM")
        app.feedback_var = FakeVariable()
        app.open_button = FakeButton()
        app.start_button = FakeButton()
        app.stop_button = FakeButton()
        app.quit_button = FakeButton()
        return app

    def process_worker_event(self, app):
        event = app.events.get(timeout=3)
        app.events.put(event)
        app.poll_events()

    def test_shutdown_failure_keeps_session_and_lock_for_retry(self):
        app = self.make_app()
        original_session = app.session

        with patch("clipshare.desktop.messagebox.showerror") as showerror:
            # Simulate a user choosing Quit; a failed stop must leave the window
            # open and must not turn the next manual retry into an automatic quit.
            app.stop_session(quit_after=True)
            self.process_worker_event(app)

            self.assertIs(app.session, original_session)
            self.assertFalse(app.busy)
            self.assertFalse(app.quit_after_stop)
            self.assertEqual(app.status_var.get().lower().count("still be running"), 1)
            self.assertEqual(app.stop_button.state, "normal")
            self.assertEqual(app.start_button.state, "disabled")
            self.assertEqual(app.open_button.state, "normal")
            self.assertEqual(app.instance_lock.states, [])
            self.assertTrue(app.root.alive)
            showerror.assert_called_once()

            app.stop_session()
            self.process_worker_event(app)

        self.assertEqual(original_session.calls, 2)
        self.assertIsNone(app.session)
        self.assertEqual(app.instance_lock.states, [{"running": False}])
        self.assertEqual(app.start_button.state, "normal")
        self.assertEqual(app.stop_button.state, "disabled")
        self.assertTrue(app.root.alive)


if __name__ == "__main__":
    unittest.main()
