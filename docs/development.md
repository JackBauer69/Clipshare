# Development and release guide

## Architecture

`src/clipshare/clipboard_share.py` owns the platform-neutral HTTP server, browser UI, pairing/authentication, upload validation, and temporary storage. `desktop.py` provides the Tkinter control window and coordinates the server lifecycle; `instance.py` provides a per-user single-instance lock. `launcher.py` is the packaged entry point, with `--version` and `--self-test` commands used by installers and CI. The browser remains the sharing interface; no tray process or background login service is used.

Stop/Quit closes the listener and removes that session's temporary files. Closing the browser leaves the control window and server running. Closing the control window asks whether to stop and quit. Operating-system logout terminates the process, and normal process shutdown cleans up the temporary directory. ClipShare does not start automatically at login.

The session pairing code is generated on each Start and displayed only in the control window. Each browser, including the host's, exchanges the code once for a random host-only `HttpOnly`, `SameSite=Strict` cookie. Content and upload/download endpoints require an authorized cookie. Pairing attempts are rate-limited by client address. The listener still uses plain HTTP on the LAN; use it only on trusted networks. There are no cloud services, telemetry, or third-party runtime APIs.

The original limits are retained: 100 text entries at up to 200 KB each, 8 MiB upload chunks, 3 GiB per batch and total temporary storage. A session may retain up to 50 upload batches, including uploads in progress. Windows-reserved path components and duplicate archive paths are rejected so ZIP downloads remain safe to extract across platforms. Empty files are supported. Text and uploaded files are removed on Stop/Quit.

## Local development and tests

Use Python 3.12 for parity with CI. Tkinter must be available in the Python installation.

From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
PYTHONPATH=src python scripts/clipboard_share.py --version
```

The HTTP tests bind loopback sockets and create temporary files. They do not require Internet access or a real LAN. On headless Linux, run the GUI smoke check under a virtual X server such as Xvfb; the normal self-test exercises the Tcl runtime and HTTP server without displaying a window.

## Native application builds

PyInstaller builds for the current operating system and CPU architecture. It is not a cross-compiler. Install the pinned build dependency, then run:

```sh
python -m pip install -r requirements-build.txt
python scripts/build_app.py
```

The frozen app is created under `build/frozen/`. Verify it with:

```sh
build/frozen/ClipShare/ClipShare --self-test
```

On Windows use `build/frozen/ClipShare/ClipShare.exe --self-test`; on macOS use `build/frozen/ClipShare.app/Contents/MacOS/ClipShare --self-test`.

### Windows installer

Build the app on Windows, install NSIS, then compile `packaging/windows/clipshare.nsi` with `PROJECT_ROOT` set to the repository root. The installer is per-user and creates a Start-menu entry. Its uninstaller removes only files present in the frozen application bundle. Signing is optional during development. A public signed installer requires the owner's code-signing certificate.

### macOS package

Build on the target native macOS architecture and run `sh packaging/macos/build_pkg.sh`. It creates a guided `.pkg` under `build/artifacts/`. Without signing configuration the package is unsigned and macOS may block or warn on first launch. For distribution, the owner must configure Developer ID application and installer identities and an Apple notary API key. The script writes a `.signing.txt` status record; release CI requires both app and installer signing plus notarization for both architectures.

### Linux packages

Build on Ubuntu 22.04 x86-64 so the frozen app uses the intended glibc baseline. Install `dpkg-deb`, `rpmbuild`, and the Tk/X11 development/runtime libraries needed by PyInstaller, then run:

```sh
python scripts/build_app.py
python scripts/package_linux.py
```

This produces a Debian `.deb` and Fedora-family `.rpm` under `build/artifacts/`. The desktop entry starts `/opt/clipshare/ClipShare`; package managers own installation and removal. AppImage is not part of the first artifact set.

## CI and release workflow

`.github/workflows/cross-platform.yml` runs the tests on Windows x64, Ubuntu 22.04 x64, macOS 15 Intel, and macOS 15 Apple Silicon. It builds artifacts on native runners, smoke-tests the installed Windows app and Linux packages, and uploads build artifacts for review. The current local session cannot run hosted GitHub Actions; configured native jobs are not evidence that those OS builds have passed until the workflow runs.

A tag matching the package version (`v0.1.0` for the current version) triggers a release job. The release job requires an owner-selected `LICENSE` file, a public `CLIPSHARE_MAINTAINER` repository variable in the form `ClipShare Team <team@example.org>`, and signed/notarized macOS packages; it fails without them. The owner must choose and add a license for the ClipShare source before publishing because GitHub also exposes source archives for releases. Do not create or push a tag as part of ordinary development.

Configure these as protected repository Actions secrets only when signing credentials are available:

- Windows: `WINDOWS_CERTIFICATE_PFX_BASE64`, `WINDOWS_CERTIFICATE_PASSWORD`.
- macOS: `APPLE_CERTIFICATE_P12_BASE64`, `APPLE_CERTIFICATE_PASSWORD`, `MACOS_KEYCHAIN_PASSWORD`, `MACOS_APPLICATION_IDENTITY`, `MACOS_INSTALLER_IDENTITY`, `APPLE_API_KEY_BASE64`, `APPLE_API_KEY_ID`, and `APPLE_API_ISSUER_ID`.

No certificate, password, API key, or token belongs in source control. Without the macOS signing and notarization secrets, CI can build unsigned packages for review, but the release job will not publish them. An unsigned Windows installer can produce a SmartScreen warning.

For Linux package metadata, set the non-secret `CLIPSHARE_MAINTAINER` repository variable before release. Development builds use an explicit `.invalid` placeholder until the owner supplies the project contact.

## Support matrix and adding targets

The intended initial targets are Windows 10/11 x64; macOS 15+ Intel and Apple Silicon; Debian 12+/Ubuntu 22.04+ x64; Fedora 45+ x64. The macOS minimum follows the configured deployment target. Linux compatibility depends on the Ubuntu 22.04 glibc baseline and the host's X11/Tk shared libraries. These are targets, not a claim of manual validation on every version.

To add an OS or architecture, add a native hosted runner to both test and package matrices, run the test suite there, add a native packaging path, and include an install/launch/uninstall smoke test. Confirm the oldest target OS and architecture before listing it as supported. Do not use a newer Linux build environment if it raises the glibc requirement above the documented minimum.

## Licensing and distribution notes

The bundle includes Python, Tcl/Tk, and PyInstaller license texts under `third_party_licenses/`. PyInstaller's bootloader exception permits distributing bundled applications. The repository currently has no source license; the project owner must select one before publishing source. RPM metadata uses a placeholder `LicenseRef` until that decision is made; update the RPM `License:` field and this notice after the owner selects a license. Release CI rejects the placeholder. NSIS and Linux package tools are build-time dependencies, not installed runtime components.
