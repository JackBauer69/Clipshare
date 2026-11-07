# ClipShare cross-platform architecture and porting plan

## Baseline

The app in `src/clipshare/clipboard_share.py` is a standard-library `ThreadingHTTPServer` with an inline HTML/CSS/JavaScript interface. It listens on `0.0.0.0:3570`, retains the newest 100 text messages (200 KB per message), and accepts chunked file/folder uploads (8 MiB chunks, 3 GiB per batch and total temporary storage). Uploaded content is held in a `TemporaryDirectory` and removed on process exit. Folder paths are retained. The existing tests exercise the HTTP page and text submission. They passed on the baseline when run with permission to bind loopback sockets.

The old `service/` code is limited to systemd, KDE/Qt, D-Bus, and Plasma. It will be removed from the active product branch after the replacement is in place; `main` remains the untouched reference.

## Chosen application architecture

```text
OS application launcher
        │
        ▼
Tkinter desktop controller ─── owns one HTTP server and temporary directory
        │                              │
        ├── opens default browser       └── standard-library HTTP handlers
        ├── displays local/LAN URLs                 │
        ├── displays session pairing code           ▼
        ├── copies URL/code                   existing browser UI
        └── Stop/Quit controls                text and file exchange
```

Use Python's standard-library `tkinter` for a small control window. It supplies native widgets on Windows, macOS, and Linux without a new application framework or third-party runtime dependency. The existing browser UI remains the sharing interface. The desktop process owns the HTTP server, so Stop and Quit can shut it down synchronously and clean temporary uploads. Closing the browser leaves the control window and server running, with the status and URLs still visible. Closing the control window asks whether to stop sharing and quit. Logging out ends the desktop process and triggers normal temporary-file cleanup. ClipShare never starts at login automatically.

On launch, the control window starts the server and opens the loopback page in the default browser. It remains open to show status and LAN connection details. Stop stops the HTTP service and removes temporary uploads while leaving the control window available; Start creates a fresh session/code and reopens the page. Quit stops sharing and exits. A per-user OS file lock prevents a second server: a second launch opens the existing page when the first instance is serving, or informs the user to use the already-open control window if it is stopped.

The HTTP core remains independent of desktop APIs. A server/session object owns its message state, temporary directory, pairing code, cookie sessions, locks, listener, and shutdown lifecycle. The desktop controller uses a small adapter around that object; platform-specific code is limited to native packaging and standard browser launch.

## Packaging and licensing choice

Use PyInstaller in `onedir` mode to bundle Python, Tcl/Tk, and the app. It is a bundler, not a cross-compiler, so each OS/architecture artifact is built on its matching native runner. `onedir` avoids repeated extraction at startup and preserves macOS app bundle layout. CI pins the build dependency and the Python version.

- Windows: NSIS guided per-user installer, Start-menu entry, optional desktop shortcut, and matching uninstaller. NSIS uses the zlib/libpng license; no signing certificate is assumed.
- macOS: native `.pkg` installer containing `ClipShare.app`, built with Apple's `pkgbuild`/`productbuild`. Intel and Apple Silicon artifacts are built separately. The build has optional Developer ID signing and `notarytool` steps driven only by protected CI secrets. Unsigned packages may trigger Gatekeeper warnings and are not a public-release-ready substitute for signing/notarization.
- Linux x86-64: `.deb` and `.rpm` packages with a desktop entry and app files under `/opt/clipshare`. The Debian package is built on the oldest supported Debian-family runner. RPM metadata is assembled with `rpmbuild` in a Fedora container and is tested in that container. Package-manager installation/removal provides the graphical OS flow; it may request administrator approval.

AppImage is deferred to avoid adding a second Linux integration format before the native packages are exercised. PyInstaller is GPLv2-or-later with an exception for distributing bundled applications; the app itself and Python/Tcl/Tk remain under their respective licenses. Build notices and licenses will be shipped with the bundle. NSIS and packaging tools are build-time tools, not runtime dependencies.

## Initial support matrix

This is the intended first-release matrix, not a claim of completed OS validation:

| Platform | Artifact | Initial target |
| --- | --- | --- |
| Windows | `ClipShare-<version>-windows-x64-setup.exe` | Windows 10/11, x86-64 |
| macOS | `ClipShare-<version>-macos-x64.pkg` | macOS 13+, Intel x86-64 |
| macOS | `ClipShare-<version>-macos-arm64.pkg` | macOS 13+, Apple Silicon |
| Debian family | `clipshare_<version>_amd64.deb` | Debian 12+, Ubuntu 22.04+, x86-64 |
| Fedora family | `clipshare-<version>-1.x86_64.rpm` | Fedora 40+, x86-64 |

Windows and macOS installer execution, older OS compatibility, and Linux package installation must be verified on the target systems before calling these supported releases. Linux binaries are built on Ubuntu 22.04 to keep their glibc baseline compatible with the stated minimum. The macOS deployment target is 13.0; runner and Python versions will be pinned so the build does not silently raise the minimum.

## Network security and privacy

The host still listens on all interfaces for LAN access and still uses plain HTTP. The redesigned session uses a cryptographically random, session-only pairing code shown in the control window. A remote browser enters that code once; the server issues a random host-only `HttpOnly`, `SameSite=Strict` cookie. All content, upload, and download routes require a valid session. The code and sessions are held only in memory and rotate on Stop/Start. Login attempts are rate-limited. No code is placed in URLs, browser history, logs, or cloud services.

This protects against accidental access by other LAN users, but not an observer who can sniff or alter traffic on an untrusted network: HTTP provides no transport encryption. UI and docs will say to share only on a trusted network. No firewall is modified. The listener first attempts port 3570 and falls back to an OS-selected free port on conflict; the actual port is shown in the control window. Uploaded files and shared messages remain temporary and are deleted at Stop/Quit.

Upload handling will reject absolute paths, traversal components, Windows drive paths, invalid sizes, excessive JSON request sizes, and out-of-order/oversized chunks. Random server-generated IDs, rather than client filenames, select disk paths. ZIP members use only validated relative names. Downloads stream to the response instead of loading a whole file into memory.

## Migration sequence

1. Refactor the existing HTTP implementation into a session-owned server factory, retaining page behavior and limits while adding pairing and input hardening.
2. Add a standard-library Tkinter controller, session lifecycle and single-instance behavior; replace the source launcher with the GUI entry point.
3. Add end-to-end tests for auth, messages, uploads, download/ZIP, validation, limits, port fallback, cleanup, and repeat launch behavior.
4. Remove Linux-only tray, lock monitor, systemd units, and KDE installer from this branch.
5. Add native package layouts/scripts and desktop metadata, then native CI matrix jobs.
6. Update consumer README and developer/release documentation; run all available tests and package smoke checks. Report OS-specific installations not performed on real systems as unverified.

## References

- [PyInstaller manual](https://pyinstaller.org/en/stable/): bundling, platform-specific builds, macOS bundles, and Linux glibc compatibility.
- [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): native Windows, Linux, Intel macOS, and Apple Silicon runner labels.
- [NSIS license](https://nsis.sourceforge.io/License): installer build-tool licensing.
- [Apple package distribution](https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution) and [notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution): signing requirements for downloaded macOS software.
