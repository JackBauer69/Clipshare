#!/usr/bin/python3
"""Remove only files managed by the Clipboard Share integration installer."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


HOME = Path.home()
INSTALL_DIRECTORY = HOME / ".local/lib/clipshare-integration"
MANIFEST = INSTALL_DIRECTORY / "managed-files.json"


def run(*args):
    return subprocess.run(args, text=True, capture_output=True)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if not MANIFEST.is_file():
        print(f"No managed installation found at {INSTALL_DIRECTORY}.")
        return 0
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    units = [Path(name).name for name in manifest["targets"]]
    for unit in units:
        result = run("systemctl", "--user", "disable", "--now", unit)
        if result.returncode and (result.stderr or result.stdout).strip():
            print(f"Notice: systemctl could not stop/disable {unit}: {(result.stderr or result.stdout).strip()}")
    run("systemctl", "--user", "daemon-reload")

    backup_dir = INSTALL_DIRECTORY / "backups"
    retained = []
    for target_name, record in manifest["targets"].items():
        target = Path(target_name)
        expected_hash = record.get("installed_sha256")
        if target.exists() and expected_hash and file_hash(target) != expected_hash:
            print(f"Keeping locally modified file: {target}")
            retained.append(target)
            continue
        backup_name = record.get("backup")
        if backup_name:
            backup = backup_dir / backup_name
            if backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                print(f"Restored previous file: {target}")
            else:
                print(f"Missing backup; leaving target untouched: {target}")
                retained.append(target)
                continue
        else:
            target.unlink(missing_ok=True)

    for name in ("tray.py", "lock_monitor.py", "managed-files.json"):
        (INSTALL_DIRECTORY / name).unlink(missing_ok=True)
    if retained:
        print("The integration backup directory is retained because a managed unit was edited:")
        for path in retained:
            print(" ", path)
        return 0
    for backup in backup_dir.iterdir() if backup_dir.exists() else ():
        backup.unlink(missing_ok=True)
    if backup_dir.exists():
        backup_dir.rmdir()
    try:
        INSTALL_DIRECTORY.rmdir()
    except OSError:
        print(f"Leaving nonempty directory with user files: {INSTALL_DIRECTORY}")
    print("Clipboard Share integration removed. The original Python application was left in place.")
    print("Its pre-change backup, if present, was also left in place.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError) as error:
        print(f"Uninstall failed: {error}", file=sys.stderr)
        raise SystemExit(1)
