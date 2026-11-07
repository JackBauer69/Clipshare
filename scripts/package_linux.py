#!/usr/bin/env python3
"""Assemble Debian and RPM packages from a Linux PyInstaller onedir build."""

from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from clipshare import __version__  # noqa: E402

DEFAULT_MAINTAINER = "ClipShare maintainers <clipshare@example.invalid>"
MAINTAINER_PATTERN = re.compile(r"^[^<>\r\n]+ <[^<>\s@]+@[^<>\s@]+>$")


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    maintainer = os.environ.get("CLIPSHARE_MAINTAINER", "").strip() or DEFAULT_MAINTAINER
    if not MAINTAINER_PATTERN.fullmatch(maintainer):
        raise SystemExit("CLIPSHARE_MAINTAINER must look like 'ClipShare maintainers <team@example.org>'.")

    bundle = ROOT / "build/frozen/ClipShare"
    executable = bundle / "ClipShare"
    if not executable.is_file():
        raise SystemExit(f"Missing Linux app bundle: {bundle}. Run scripts/build_app.py first.")
    artifacts = ROOT / "build/artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="clipshare-package-") as temporary:
        temporary = Path(temporary)
        deb_root = temporary / "deb-root"
        app_root = deb_root / "opt/clipshare"
        app_root.parent.mkdir(parents=True)
        shutil.copytree(bundle, app_root, symlinks=True)
        desktop_target = deb_root / "usr/share/applications/clipshare.desktop"
        desktop_target.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "packaging/linux/clipshare.desktop", desktop_target)

        control = deb_root / "DEBIAN/control"
        control.parent.mkdir(parents=True)
        control.write_text(
            f"""Package: clipshare
Version: {__version__}
Section: net
Priority: optional
Architecture: amd64
Maintainer: {maintainer}
Depends: libc6 (>= 2.35), libx11-6, libxext6, libxft2, libxrender1, libxss1
Description: Temporary local-network text and file sharing
 Share text, files, and folders with other devices on a trusted LAN.
 Shared messages and uploaded files are deleted when the app stops.
""",
            encoding="utf-8",
        )
        deb_path = artifacts / f"clipshare_{__version__}_amd64.deb"
        run("dpkg-deb", "--root-owner-group", "--build", str(deb_root), str(deb_path))

        rpm_top = temporary / "rpmbuild"
        source_dir = rpm_top / "SOURCES"
        rpm_output = rpm_top / "RPMS"
        source_dir.mkdir(parents=True)
        for directory in ("BUILD", "BUILDROOT", "SPECS", "SRPMS", "TMP", "rpmdb"):
            (rpm_top / directory).mkdir(exist_ok=True)
        rpm_output.mkdir(parents=True, exist_ok=True)
        bundle_archive = source_dir / "clipshare-bundle.tar.gz"
        with tarfile.open(bundle_archive, "w:gz") as archive:
            archive.add(bundle, arcname="clipshare")
        shutil.copy2(ROOT / "packaging/linux/clipshare.desktop", source_dir / "clipshare.desktop")
        spec = ROOT / "packaging/linux/clipshare.spec"
        run(
            "rpmbuild",
            "-bb",
            "--define",
            f"_topdir {rpm_top}",
            "--define",
            f"_rpmdir {rpm_output}",
            "--define",
            f"_dbpath {rpm_top / 'rpmdb'}",
            "--define",
            f"_tmppath {rpm_top / 'TMP'}",
            "--define",
            f"clipshare_version {__version__}",
            "--define",
            f"clipshare_maintainer {maintainer}",
            str(spec),
        )
        built_rpms = list(rpm_output.rglob(f"clipshare-{__version__}-1*.rpm"))
        if not built_rpms:
            raise SystemExit("rpmbuild completed without producing a ClipShare RPM")
        for rpm in built_rpms:
            target = artifacts / rpm.name
            if rpm != target:
                shutil.move(rpm, target)
    print(f"Created {deb_path} and RPM package(s) in {artifacts}.")


if __name__ == "__main__":
    main()
