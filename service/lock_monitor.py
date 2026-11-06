#!/usr/bin/python3
"""Stop Clipboard Share when Plasma reports that the screen is locking."""

import subprocess
import sys

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


SERVICE = "clipshare.service"


class LockMonitor:
    def __init__(self, bus):
        self.bus = bus
        self.lock_stop_requested = False
        bus.add_signal_receiver(
            self.active_changed,
            signal_name="ActiveChanged",
            dbus_interface="org.freedesktop.ScreenSaver",
            path="/ScreenSaver",
        )
        bus.add_signal_receiver(
            self.about_to_lock,
            signal_name="AboutToLock",
            dbus_interface="org.kde.screensaver",
            path="/ScreenSaver",
        )

    def stop_sharing(self, reason):
        if self.lock_stop_requested:
            return
        self.lock_stop_requested = True
        try:
            result = subprocess.run(
                ["systemctl", "--user", "stop", SERVICE],
                text=True,
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"Could not stop {SERVICE} on lock ({reason}): {error}", flush=True)
            return
        if result.returncode == 0:
            print(f"Stopped {SERVICE} on screen lock ({reason}).", flush=True)
        else:
            print(
                f"systemctl stop {SERVICE} failed on screen lock ({reason}): "
                f"{result.stderr.strip() or result.stdout.strip()}",
                flush=True,
            )

    def active_changed(self, active):
        if bool(active):
            self.stop_sharing("ActiveChanged(true)")
        else:
            # Unlocking only resets event de-duplication; it never starts sharing.
            self.lock_stop_requested = False

    def about_to_lock(self):
        self.stop_sharing("AboutToLock")

    def check_initial_state(self):
        try:
            screensaver = self.bus.get_object("org.kde.screensaver", "/ScreenSaver")
            interface = dbus.Interface(screensaver, "org.freedesktop.ScreenSaver")
            if bool(interface.GetActive(timeout=3)):
                self.stop_sharing("initial state is locked")
                return
            print("Screen lock monitor ready; screen is unlocked.", flush=True)
        except dbus.DBusException as error:
            # Signal subscriptions remain active even if the locker starts later.
            print(f"Could not query initial lock state; listening for lock signals: {error}", flush=True)


def main():
    try:
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        monitor = LockMonitor(bus)
        monitor.check_initial_state()
        GLib.MainLoop().run()
    except (dbus.DBusException, GLib.Error) as error:
        print(f"Clipboard Share lock monitor could not connect to the session bus: {error}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
