"""Small per-user process lock for the desktop application."""

import getpass
import hashlib
import json
import os
from pathlib import Path
import tempfile


def lock_path():
    if hasattr(os, "getuid"):
        identity = f"uid-{os.getuid()}"
        directory = Path(tempfile.gettempdir()) / f"clipshare-{identity}"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        details = directory.stat()
        if details.st_uid != os.getuid() or details.st_mode & 0o077:
            raise PermissionError("ClipShare's private temporary lock directory is not secure.")
    else:
        identity = "user-" + hashlib.sha256(getpass.getuser().encode("utf-8")).hexdigest()[:16]
        directory = Path(tempfile.gettempdir())
    return directory / f"clipshare-{identity}.lock"


class SingleInstanceLock:
    def __init__(self, path=None):
        self.path = Path(path) if path else lock_path()
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+", encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
            if os.name == "nt":
                import msvcrt

                self.file.seek(0, os.SEEK_END)
                if self.file.tell() == 0:
                    self.file.write(" ")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.file.close()
            self.file = None
            return False
        return True

    def write_state(self, state):
        if self.file is None:
            return
        self.file.seek(0)
        self.file.truncate()
        json.dump(state, self.file)
        self.file.flush()

    def read_state(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def release(self):
        if self.file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None
