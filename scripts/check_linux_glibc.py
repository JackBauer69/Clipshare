#!/usr/bin/env python3
"""Fail if any ELF object in a bundle requires newer GLIBC symbol versions."""

import argparse
from pathlib import Path
import re
import subprocess
import sys


GLIBC_REQUIREMENT = re.compile(r"Name: GLIBC_([0-9]+(?:\.[0-9]+)+)")


def version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def elf_glibc_requirements(path):
    result = subprocess.run(
        ["readelf", "--version-info", "--wide", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    in_needs_section = False
    requirements = []
    for line in result.stdout.splitlines():
        if line.startswith("Version needs section"):
            in_needs_section = True
        elif line.startswith("Version definition section"):
            in_needs_section = False
        if in_needs_section:
            requirements.extend(GLIBC_REQUIREMENT.findall(line))
    return requirements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="PyInstaller onedir bundle to inspect")
    parser.add_argument("--maximum", default="2.35", help="maximum permitted GLIBC version (default: 2.35)")
    args = parser.parse_args()
    if not args.bundle.is_dir():
        parser.error(f"bundle directory does not exist: {args.bundle}")

    maximum = version_tuple(args.maximum)
    violations = []
    highest = None
    highest_path = None
    elf_count = 0
    for path in args.bundle.rglob("*"):
        if not path.is_file():
            continue
        try:
            with path.open("rb") as executable:
                if executable.read(4) != b"\x7fELF":
                    continue
        except OSError as error:
            parser.error(f"could not inspect {path}: {error}")
        elf_count += 1
        try:
            requirements = elf_glibc_requirements(path)
        except (OSError, subprocess.CalledProcessError) as error:
            parser.error(f"readelf could not inspect {path}: {error}")
        for requirement in requirements:
            parsed = version_tuple(requirement)
            if highest is None or parsed > highest:
                highest, highest_path = parsed, path
            if parsed > maximum:
                violations.append((parsed, path))

    if elf_count == 0:
        parser.error(f"no ELF objects found in {args.bundle}")
    if violations:
        print(f"Bundle exceeds GLIBC_{args.maximum}; highest requirements:", file=sys.stderr)
        unique_violations = {(version, str(path)): path for version, path in violations}
        for (version, _path_text), path in sorted(unique_violations.items(), reverse=True):
            print(f"  GLIBC_{'.'.join(map(str, version))}: {path}", file=sys.stderr)
        return 1

    label = ".".join(map(str, highest)) if highest else "none"
    print(f"Inspected {elf_count} ELF objects; maximum GLIBC requirement is {label} ({highest_path or 'no versioned GLIBC symbols'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
