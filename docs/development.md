# Development and release guide

## Architecture

`src/clipshare/clipboard_share.py` owns the platform-neutral HTTP server, browser UI, pairing/authentication, upload validation, and temporary storage. `desktop.py` provides the Tkinter control window and coordinates the server lifecycle; `instance.py` provides a per-user single-instance lock. `launcher.py` is the packaged entry point, with `--version` and `--self-test` commands used by installers and CI. The browser remains the sharing interface; no tray process or background login service is used.

Stop/Quit closes the listener and removes that session's temporary files. Closing the browser leaves the control window and server running. Closing the control window asks whether to stop and quit. Operating-system logout terminates the process, and normal process shutdown cleans up the temporary directory. ClipShare does not start automatically at login.

The session pairing code is generated on each Start and displayed only in the control window. Each browser, including the host's, exchanges the code once for a random host-only `HttpOnly`, `SameSite=Strict` cookie. Content and upload/download endpoints require an authorized cookie. Pairing attempts are rate-limited by client address. The listener still uses plain HTTP on the LAN; use it only on trusted networks. There are no cloud services, telemetry, or third-party runtime APIs.

The original limits are retained: 100 text entries at up to 200 KB each, 8 MiB upload chunks, 3 GiB per batch and total temporary storage. A session may retain up to 50 upload batches, including uploads in progress; each batch is limited to 1,000 files, including empty files. Windows-reserved path components and duplicate archive paths are rejected so ZIP downloads remain safe to extract across platforms. Text and uploaded files are removed on Stop/Quit.

## Local development and tests

The cross-platform test matrix uses Python 3.12. Tkinter must be available in the Python installation. Linux package builds intentionally use Ubuntu 22.04's system Python 3.10 and system Tcl/Tk so the frozen libraries match the oldest supported glibc baseline.

From the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
PYTHONPATH=src python scripts/clipboard_share.py --version
```

The HTTP tests bind loopback sockets and create temporary files. They do not require Internet access or a real LAN. Linux CI also runs `tests/gui_smoke.py` with Ubuntu 22.04's system Python 3.10 and Xvfb to open and operate the actual Tk window. Windows and macOS CI run the platform-neutral tests but do not run an actual Tk window smoke test. The packaged `--self-test` exercises Tcl and HTTP without displaying a window.

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

Build on Ubuntu 22.04 x86-64 with its system Python 3.10.x so the frozen app and bundled Tcl/Tk use the intended glibc baseline. Install `dpkg-deb`, `rpmbuild`, `binutils`, and the Tk/X11 development/runtime libraries needed by PyInstaller, then run:

```sh
python3 --version
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
.build-venv/bin/python scripts/build_app.py
.build-venv/bin/python scripts/check_linux_glibc.py build/frozen/ClipShare --maximum 2.35
.build-venv/bin/python scripts/package_linux.py
```

This produces a Debian `.deb` and Fedora-family `.rpm` under `build/artifacts/`. CI checks the extracted Debian executable on the Ubuntu 22.04 runner that built it, then installs the RPM in a Fedora 45 container and runs its self-test. The desktop entry starts `/opt/clipshare/ClipShare`; package managers own installation and removal. AppImage is not part of the first artifact set.

PyInstaller includes Tcl/Tk and other native libraries from its build host. The compatibility check inspects every ELF object's GLIBC version requirements and rejects anything newer than 2.35. A developer build made on this Kali host with Python 3.14 and glibc 2.43 has a bundled `libtcl8.6.so` requiring `GLIBC_2.42`; it is not a Debian 12/Ubuntu 22.04 distribution artifact and must not be used to infer support for those targets. Do not build release Linux packages on a newer host and compensate by changing package metadata.

RPM requirements were inspected with `rpm -qp --requires` and `--provides`. The PyInstaller bundle provides its own versioned X11, Xss, Tcl/Tk, fontconfig, and freetype libraries; RPM's ELF scanner also records those library requirements, which the same package satisfies. `libxcb.so.1` is not bundled and remains an automatic host dependency. Explicit package-name requirements for bundled `libX11`, `libXext`, `libXft`, and `libXrender` were removed. CI asserts the bundled libraries are both required and provided by the RPM, confirms the external `libxcb.so.1` requirement, and installs the package in Fedora 45. That Fedora transaction has not been run locally.

## CI and release workflow

`.github/workflows/cross-platform.yml` runs the tests on Windows x64, Ubuntu 22.04 x64, macOS 15 Intel, and macOS 15 Apple Silicon using Python 3.12. Linux package creation is a deliberate exception: on Ubuntu 22.04 it uses system Python 3.10 and system Tcl/Tk, enforces a GLIBC 2.35 maximum, and smoke-tests the extracted `.deb` on that baseline. It also installs and smoke-tests the `.rpm` in Fedora 45. Windows and macOS use native Python 3.12 builds. GitHub Actions run [#42560420432](https://github.com/JackBauer69/clipshare/actions/runs/42560420432) passed all eight tests/package jobs. The owner installed the resulting `.deb` on Kali Linux and verified real sharing. Those results verify the build pipeline and Kali test, but do not replace manual installation and UI/network testing on physical Windows and macOS systems.

A tag matching the package version (`v0.1.0` for the current version) triggers a release job. The release job requires an owner-selected `LICENSE` file, a public `CLIPSHARE_MAINTAINER` repository variable in the form `ClipShare Team <team@example.org>`, and signed/notarized macOS packages; it fails without them. The owner must choose and add a license for the ClipShare source before publishing because GitHub also exposes source archives for releases. Do not create or push a tag as part of ordinary development.

Configure these as protected repository Actions secrets only when signing credentials are available:

- Windows: `WINDOWS_CERTIFICATE_PFX_BASE64`, `WINDOWS_CERTIFICATE_PASSWORD`.
- macOS: `APPLE_CERTIFICATE_P12_BASE64`, `APPLE_CERTIFICATE_PASSWORD`, `MACOS_KEYCHAIN_PASSWORD`, `MACOS_APPLICATION_IDENTITY`, `MACOS_INSTALLER_IDENTITY`, `APPLE_API_KEY_BASE64`, `APPLE_API_KEY_ID`, and `APPLE_API_ISSUER_ID`.

No certificate, password, API key, or token belongs in source control. Without the macOS signing and notarization secrets, CI can build unsigned packages for review, but the release job will not publish them. An unsigned Windows installer can produce a SmartScreen warning.

For Linux package metadata, set the non-secret `CLIPSHARE_MAINTAINER` repository variable before release. Development builds use an explicit `.invalid` placeholder until the owner supplies the project contact.

## First public release checklist

The repository remains private and no official public release has been published. Before publishing `v0.1.0`:

1. Change the repository default branch to `main` (Settings → General → Default branch), after confirming the merged cross-platform tree.
2. The owner has chosen to retain proprietary source-code rights for now. Obtain legal review of end-user permission for official binaries, permitted personal changes, commercial redistribution and derivative-code licensing; then add approved legal terms in the correct files, update the RPM `License:` field and third-party notices. See `LICENSING.md`. Do not treat the current rights statement as a completed EULA or an open-source license.
3. Set the non-secret `CLIPSHARE_MAINTAINER` repository Actions variable to a real project contact.
4. Manually install, use, and uninstall the Windows and macOS packages on supported computers; exercise pairing, file/text sharing, stop/restart, and cleanup. Keep the Kali Linux result as separately documented validation.
5. Configure macOS Developer ID signing and notarization. The tag-triggered release job deliberately refuses to publish unsigned or unnotarized macOS installers.
6. Decide whether to sign Windows installers to reduce SmartScreen prompts, review release notes and supported-OS claims, and ensure no secrets or personal files are in the repository.
7. Only after these gates are met, deliberately create and push the `v0.1.0` tag and confirm the official GitHub Release contains the correct installers.

Ordinary pull requests and CI build artifacts are not public releases. Do not bypass the release workflow's licensing/signing checks to publish early.

## Support matrix and adding targets

The intended initial targets are Windows 10/11 x64; macOS 15+ Intel and Apple Silicon; Debian 12+/Ubuntu 22.04+ x64; Fedora 45+ x64. The macOS minimum follows the configured deployment target. Linux compatibility depends on the Ubuntu 22.04 glibc baseline and the host's X11/Tk shared libraries. These are targets, not a claim of manual validation on every version.

To add an OS or architecture, add a native hosted runner to both test and package matrices, run the test suite there, add a native packaging path, and include an install/launch/uninstall smoke test. Confirm the oldest target OS and architecture before listing it as supported. Do not use a newer Linux build environment if it raises the glibc requirement above the documented minimum.

## Licensing and distribution notes

The bundle includes Python, Tcl/Tk, and PyInstaller license texts under `third_party_licenses/`. PyInstaller's bootloader exception permits distributing bundled applications. The owner has selected proprietary rights for the original source code; `LICENSING.md` documents that intent, but it is not a legally reviewed end-user or commercial-license agreement. The repository has no `LICENSE` file yet; final terms must be approved before public distribution. RPM metadata uses a placeholder `LicenseRef` pending those terms; update the RPM `License:` field and this notice when the legal distribution terms are ready. Release CI rejects the placeholder. NSIS and Linux package tools are build-time dependencies, not installed runtime components.
