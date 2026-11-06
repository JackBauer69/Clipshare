#!/usr/bin/python3
"""Install the Clipboard Share KDE/systemd user integration."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SOURCE = Path(__file__).resolve().parent
PROJECT_ROOT = SOURCE.parent
HOME = Path.home()
APP_SCRIPT = PROJECT_ROOT / "src/clipshare/clipboard_share.py"
INSTALL_DIRECTORY = HOME / ".local/lib/clipshare-integration"
SERVICE_DIRECTORY = HOME / ".config/systemd/user"
MANIFEST = INSTALL_DIRECTORY / "managed-files.json"
UNITS = {
    "clipshare.service": SOURCE / "clipshare.service.in",
    "clipshare-tray.service": SOURCE / "clipshare-tray.service.in",
    "clipshare-lock-monitor.service": SOURCE / "clipshare-lock-monitor.service.in",
}
TARGETS = {
    SERVICE_DIRECTORY / name: template for name, template in UNITS.items()
}


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True)
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")
    return result


def check_environment():
    if os.geteuid() == 0:
        raise RuntimeError("Run this installer as your normal desktop user, not as root.")
    os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    distro_id = next((line.split("=", 1)[1].strip('"') for line in os_release.splitlines() if line.startswith("ID=")), "")
    if distro_id not in {"kali", "debian"}:
        print(f"Notice: this installer was designed for Kali/Debian (detected {distro_id or 'unknown'}).")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "") + " " + os.environ.get("KDE_SESSION_VERSION", "")
    if "kde" not in desktop.lower() and not os.environ.get("KDE_FULL_SESSION"):
        raise RuntimeError("A KDE Plasma desktop session is required. Run this from your Plasma session.")
    if not APP_SCRIPT.is_file() or not os.access(APP_SCRIPT, os.X_OK):
        raise RuntimeError(f"The executable application was not found: {APP_SCRIPT}")
    app_source = APP_SCRIPT.read_text(encoding="utf-8")
    if "signal.signal(signal.SIGTERM" not in app_source:
        raise RuntimeError("The application lacks the SIGTERM cleanup handler required by the service.")
    for name in UNITS.values():
        if not name.is_file():
            raise RuntimeError(f"Missing integration file: {name}")
    run(
        "/usr/bin/python3",
        "-c",
        "import PySide6.QtWidgets, dbus.mainloop.glib; from gi.repository import GLib",
    )
    run("systemctl", "--user", "show-environment")
    if INSTALL_DIRECTORY.exists() and not MANIFEST.is_file():
        if any(INSTALL_DIRECTORY.iterdir()):
            raise RuntimeError(f"Refusing to overwrite an unmanaged directory: {INSTALL_DIRECTORY}")


def systemd_quote(value):
    value = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{value}"'


def systemd_path(value):
    value = str(value).replace("%", "%%").replace("\\", "\\\\")
    return value.replace(" ", "\\x20").replace('"', "\\x22").replace("\t", "\\x09")


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path, contents, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(contents)
        temp_path = Path(temporary.name)
    temp_path.chmod(mode)
    temp_path.replace(path)


def main():
    check_environment()
    INSTALL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    backup_dir = INSTALL_DIRECTORY / "backups"
    backup_dir.mkdir(exist_ok=True)

    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = {"version": 1, "targets": {}}
    for target in TARGETS:
        key = str(target)
        if key not in manifest["targets"]:
            backup_name = None
            if target.exists():
                backup_name = f"{target.name}.original"
                shutil.copy2(target, backup_dir / backup_name)
            manifest["targets"][key] = {"backup": backup_name, "installed_sha256": None}
    atomic_write(MANIFEST, json.dumps(manifest, indent=2) + "\n", 0o600)

    for source_name in ("tray.py", "lock_monitor.py"):
        installed = INSTALL_DIRECTORY / source_name
        shutil.copy2(SOURCE / source_name, installed)
        installed.chmod(0o755)

    replacements = {
        "@APP_SCRIPT@": systemd_quote(APP_SCRIPT),
        "@APP_DIRECTORY@": systemd_path(APP_SCRIPT.parent),
        "@TRAY_SCRIPT@": systemd_quote(INSTALL_DIRECTORY / "tray.py"),
        "@LOCK_MONITOR@": systemd_quote(INSTALL_DIRECTORY / "lock_monitor.py"),
    }
    SERVICE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for target, template in TARGETS.items():
        contents = template.read_text(encoding="utf-8")
        for placeholder, value in replacements.items():
            contents = contents.replace(placeholder, value)
        atomic_write(target, contents)
        manifest["targets"][str(target)]["installed_sha256"] = file_hash(target)
    atomic_write(MANIFEST, json.dumps(manifest, indent=2) + "\n", 0o600)

    run("systemd-analyze", "verify", *[str(target) for target in TARGETS])
    run("systemctl", "--user", "daemon-reload")
    # These helpers follow the desktop session. The sharing server itself stays disabled.
    run("systemctl", "--user", "enable", "--now", "clipshare-lock-monitor.service", "clipshare-tray.service")
    print("Clipboard Share integration installed.")
    print("The tray and lock monitor are enabled for the Plasma session.")
    print("File sharing remains disabled until you run: systemctl --user start clipshare")
    print("Enable optional login startup with: systemctl --user enable clipshare")
    print("The original application remains at:", APP_SCRIPT)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
