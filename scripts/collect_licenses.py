#!/usr/bin/env python3
"""Copy the bundled runtime and bootloader license texts into a build output."""

from importlib import metadata
from pathlib import Path
import shutil
import sys
import sysconfig
import tkinter


ROOT = Path(__file__).resolve().parents[1]


def first_existing(candidates, description):
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(f"Could not locate the {description} license from this Python build.")


def tcltk_candidates(library, name):
    candidates = [
        library / "license.terms",
        library.parent / name / "license.terms",
        library.parent / "license.terms",
        Path(sys.base_prefix) / "tcl" / name / "license.terms",
        Path(sys.base_prefix) / "lib" / name / "license.terms",
        Path(sys.base_prefix) / "Library" / "lib" / name / "license.terms",
        Path(sysconfig.get_paths()["stdlib"]) / "tkinter" / "license.terms",
    ]
    docs = Path("/usr/share/doc")
    if docs.is_dir():
        candidates.extend((docs / name / "copyright", docs / name.replace("tcl", "tk") / "copyright"))
    return candidates


def copy_pyinstaller_notices(target):
    distribution = metadata.distribution("PyInstaller")
    license_files = [
        distribution.locate_file(file)
        for file in (distribution.files or ())
        if ".dist-info/licenses/" in str(file).replace("\\", "/")
    ]
    if not license_files:
        license_files = [
            distribution.locate_file(file)
            for file in (distribution.files or ())
            if Path(str(file)).name.lower() in {"copying.txt", "license", "license.txt"}
        ]
    if not license_files:
        license_files = list(dict.fromkeys(
            candidate
            for candidate in (
                Path(sys.prefix) / "share/doc/python3-pyinstaller/copyright",
                Path(sys.base_prefix) / "share/doc/python3-pyinstaller/copyright",
                Path("/usr/share/doc/python3-pyinstaller/copyright"),
                Path("/usr/share/doc/pyinstaller/copyright"),
            )
            if candidate.is_file()
        ))
    if not license_files:
        raise SystemExit("Could not locate PyInstaller's license text in the build environment.")
    license_files = list(dict.fromkeys(Path(path).resolve() for path in license_files))
    for index, source in enumerate(license_files, start=1):
        shutil.copy2(source, target / f"PyInstaller-{index}-{Path(source).name}")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: collect_licenses.py TARGET_DIRECTORY")
    target = Path(sys.argv[1])
    target.mkdir(parents=True, exist_ok=True)
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    python_license = first_existing(
        (Path(sys.base_prefix) / "LICENSE", stdlib / "LICENSE.txt", stdlib / "LICENSE"),
        "Python",
    )
    shutil.copy2(python_license, target / "Python-LICENSE.txt")

    library = Path(tkinter.Tcl().eval("info library"))
    for name in ("tcl8.6", "tk8.6"):
        license_path = first_existing(tcltk_candidates(library, name), f"{name}")
        shutil.copy2(license_path, target / f"{name.upper()}-LICENSE.txt")

    copy_pyinstaller_notices(target)
    shutil.copy2(ROOT / "packaging/licenses/THIRD_PARTY_NOTICES.md", target / "THIRD_PARTY_NOTICES.md")


if __name__ == "__main__":
    main()
