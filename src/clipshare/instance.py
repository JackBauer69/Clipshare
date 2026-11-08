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
        # State must remain readable through another handle while the lock
        # byte is held. Windows locks the byte range against reads as well.
        self.state_path = self.path.with_name(self.path.name + ".state")
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
        try:
            # Replace stale state left by an earlier process before startup.
            self.write_state({"running": False})
        except OSError:
            self.release()
            raise
        return True

    def write_state(self, state):
        if self.file is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=self.state_path.name + ".",
            suffix=".tmp",
            dir=self.state_path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(state, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.state_path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    def read_state(self):
        # The lock file may contain state from an older ClipShare process.
        # Prefer the separate state file, which remains readable on Windows.
        for path in (self.state_path, self.path):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
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
