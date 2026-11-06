#!/usr/bin/python3
"""KDE Plasma tray controller for the clipshare systemd user service."""

from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QLockFile, QStandardPaths, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
)


SERVICE = "clipshare.service"
APP_SCRIPT = Path.home() / "Projects/clipshare/src/clipshare/clipboard_share.py"


def command(*args, timeout=8):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout)


class TrayController:
    def __init__(self, app):
        self.app = app
        self.tray = QSystemTrayIcon()
        self.menu = QMenu()

        self.start_action = QAction("Start File Sharing", self.menu)
        self.stop_action = QAction("Stop File Sharing", self.menu)
        self.restart_action = QAction("Restart File Sharing", self.menu)
        self.start_action.triggered.connect(lambda: self.service_action("start"))
        self.stop_action.triggered.connect(lambda: self.service_action("stop"))
        self.restart_action.triggered.connect(lambda: self.service_action("restart"))
        self.menu.addAction(self.start_action)
        self.menu.addAction(self.stop_action)
        self.menu.addAction(self.restart_action)
        self.menu.addSeparator()
        self.menu.addAction("Show Service Status", self.show_status)
        self.menu.addAction("View Logs", self.show_logs)
        self.menu.addAction("Open Application Configuration", self.show_configuration)
        self.menu.addSeparator()
        self.menu.addAction("Quit Tray", self.app.quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_activated)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)
        self.refresh()
        self.tray.show()

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_status()

    def active_state(self):
        try:
            result = command("systemctl", "--user", "show", SERVICE, "--property=ActiveState", "--value")
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable"
        if result.returncode != 0:
            return "missing"
        return result.stdout.strip() or "unknown"

    def make_icon(self, running):
        base = QIcon.fromTheme("network-server")
        if base.isNull():
            base = self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        pixmap = base.pixmap(32, 32)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#202124"), 1.5))
        painter.setBrush(QColor("#35a853" if running else "#d93025"))
        painter.drawEllipse(20, 20, 11, 11)
        painter.end()
        return QIcon(pixmap)

    def refresh(self):
        state = self.active_state()
        running = state == "active"
        self.tray.setIcon(self.make_icon(running))
        self.tray.setToolTip(f"Clipboard Share: {state}")
        self.start_action.setEnabled(state != "active")
        self.stop_action.setEnabled(state in ("active", "activating", "reloading"))
        self.restart_action.setEnabled(state not in ("missing", "unavailable"))

    def service_action(self, action):
        try:
            result = command("systemctl", "--user", action, SERVICE, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as error:
            QMessageBox.critical(None, "Clipboard Share", str(error))
            return
        if result.returncode:
            QMessageBox.critical(None, "Clipboard Share", result.stderr.strip() or result.stdout.strip())
        self.refresh()

    def show_status(self):
        try:
            result = command("systemctl", "--user", "status", SERVICE, "--no-pager", "-l")
        except (OSError, subprocess.TimeoutExpired) as error:
            QMessageBox.critical(None, "Clipboard Share status", str(error))
            return
        text = (result.stdout + result.stderr).strip() or "No status output."
        QMessageBox.information(None, "Clipboard Share status", text)

    def show_logs(self):
        dialog = QDialog()
        dialog.setWindowTitle("Clipboard Share logs")
        dialog.resize(760, 480)
        layout = QVBoxLayout(dialog)
        output = QPlainTextEdit()
        output.setReadOnly(True)
        layout.addWidget(output)
        buttons = QHBoxLayout()
        refresh_button = QPushButton("Refresh")
        close_button = QPushButton("Close")
        buttons.addWidget(refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        def load_logs():
            try:
                result = command("journalctl", "--user", "-u", SERVICE, "-n", "150", "--no-pager")
                output.setPlainText((result.stdout + result.stderr).strip() or "No log entries yet.")
                output.moveCursor(QTextCursor.MoveOperation.End)
            except (OSError, subprocess.TimeoutExpired) as error:
                output.setPlainText(str(error))

        refresh_button.clicked.connect(load_logs)
        close_button.clicked.connect(dialog.accept)
        load_logs()
        dialog.exec()

    def show_configuration(self):
        QMessageBox.information(
            None,
            "Clipboard Share configuration",
            "This application has no separate configuration file. Its current settings are in:\n\n"
            f"{APP_SCRIPT}\n\n"
            "The service uses the script's existing port and network binding.",
        )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Clipboard Share")
    app.setQuitOnLastWindowClosed(False)

    cache_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(cache_dir / "tray.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(None, "Clipboard Share", "The Plasma system tray is not available yet.")
        return 1

    TrayController(app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
