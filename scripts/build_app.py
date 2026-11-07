#!/usr/bin/env python3
"""Build a native frozen app bundle for the current operating system."""

from pathlib import Path
import platform
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from clipshare import __version__  # noqa: E402


def write_nsis_uninstall_manifest(bundle):
    """Generate precise uninstall commands for the frozen Windows bundle."""
    output = ROOT / "build/spec/clipshare_uninstall.nsh"
    output.parent.mkdir(parents=True, exist_ok=True)

    def nsis_path(path):
        relative = path.relative_to(bundle).as_posix().replace("/", "\\")
        return relative.replace("$", "$$").replace('"', '$\\"')

    files = sorted(
        (path for path in bundle.rglob("*") if path.is_file() or path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    directories = sorted(
        (path for path in bundle.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    lines = ["; Generated from the exact PyInstaller bundle contents. Do not edit.", "Function un.RemoveBundleFiles"]
    lines.extend(f'Delete "$INSTDIR\\{nsis_path(path)}"' for path in files)
    lines.extend(f'RMDir "$INSTDIR\\{nsis_path(path)}"' for path in directories)
    lines.append('RMDir "$INSTDIR"')
    lines.append("FunctionEnd")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "ClipShare",
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(ROOT / "build/frozen"),
        "--specpath",
        str(ROOT / "build/spec"),
        "--workpath",
        str(ROOT / "build/work"),
    ]
    if platform.system() == "Darwin":
        command.extend(("--osx-bundle-identifier", "org.clipshare.desktop"))
    command.append(str(ROOT / "scripts/clipboard_share.py"))
    subprocess.run(command, cwd=ROOT, check=True)
    if platform.system() == "Darwin":
        app_bundle = ROOT / "build/frozen/ClipShare.app"
        target = app_bundle / "Contents/Resources/third_party_licenses"
    else:
        target = ROOT / "build/frozen/ClipShare/third_party_licenses"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/collect_licenses.py"), str(target)],
        cwd=ROOT,
        check=True,
    )
    if platform.system() == "Windows":
        write_nsis_uninstall_manifest(ROOT / "build/frozen/ClipShare")
    print(f"Built ClipShare {__version__} for {platform.system()} {platform.machine()}.")


if __name__ == "__main__":
    main()
