# ClipShare

ClipShare lets you share text, files, and folders between devices that can reach the same local network. The host opens a small desktop control window and automatically authorizes the sharing page in your default browser. Other devices open the LAN address shown in that window and enter a temporary four-digit pairing code.

ClipShare is **not** an automatic operating-system clipboard synchronizer. It does not watch your clipboard or copy content to other devices in the background.

## Downloads and supported systems

The first release is being prepared for these 64-bit systems:

| System | Installer | Intended minimum |
| --- | --- | --- |
| Windows x64 | Guided per-user `.exe` installer | Windows 10 or 11 |
| macOS Intel | Guided `.pkg` installer | macOS 15 or later |
| macOS Apple Silicon | Guided `.pkg` installer | macOS 15 or later |
| Debian/Ubuntu x64 | `.deb` package | Debian 12 or Ubuntu 22.04 or later |
| Fedora x64 | `.rpm` package | Fedora 45 or later |

These are the intended release targets. GitHub Actions has successfully completed automated tests and packaging for Windows x64, macOS Intel, macOS Apple Silicon, and Linux x64, including package smoke tests (run [#42560420432](https://github.com/JackBauer69/clipshare/actions/runs/42560420432)). The owner has also installed the Linux `.deb` on Kali Linux and confirmed real device-to-device sharing. The owner has also installed the Windows installer successfully in a Windows VM. Windows file-sharing functionality and Windows uninstall/reinstall have not yet been separately confirmed; macOS has not been manually tested on physical machines. These builds are workflow artifacts, **not** a published release. A public release will appear on the project's GitHub **Releases** page only after the owner publishes one; do not download installers from unofficial sources.

## License

ClipShare's original source code is available under the [MIT License](LICENSE), which permits commercial use, modification, and redistribution when required notices are retained. See [LICENSING.md](LICENSING.md) for a summary. Bundled third-party components retain their own licenses.

## Development-build downloads

For private testing, the owner and authorized repository collaborators can download the four ZIP artifact groups from the successful [GitHub Actions run #42560420432](https://github.com/JackBauer69/clipshare/actions/runs/42560420432) under **Artifacts**. The ZIP groups contain the Windows `.exe`, Linux `.deb` and `.rpm`, and the two macOS `.pkg` installers. Artifacts have limited retention and are not permanent public download URLs.

These test installers may be unsigned. The official public release is **not yet available**, and macOS signing/notarization is still needed for the existing all-platform release workflow.

## Install and use

1. Download the installer matching your operating system and processor from a published GitHub Release.
2. Open it and follow the normal installer prompts. Windows installs for the current user; macOS installs ClipShare in Applications; Linux package managers install the application and add it to the application menu.
3. Launch **ClipShare** from the Start menu, Applications, or Linux application menu. The control window starts a temporary sharing session and automatically signs in the default browser through a one-use localhost link. No code entry is needed on the host browser.
4. On another device on the same reachable network, open the **LAN address** shown in the control window and enter the four-digit session code. You can use the buttons to copy either value.
5. Choose **Stop sharing** when you are done. **Quit** or closing the control window asks whether to stop and remove the session.

Closing the browser does not stop sharing; the control window stays open so you can check the status or reopen the page. Logging out ends the desktop app and its session. ClipShare does not start automatically when you sign in.

## Privacy and network access

A random four-digit code is generated for each start. A joining device enters it once; ClipShare uses a temporary browser cookie to authorize that browser. The desktop application opens its local browser with a single-use, short-lived login link so the host does not have to type a code. Pairing guesses are throttled both per address and across the session, but four digits are intentionally a convenience/security tradeoff. The code and session data stay on the host. There are no accounts, cloud storage, analytics, or external services required after installation.

Each file or folder upload batch can contain up to 1,000 files and 3 GB of data.

ClipShare uses plain HTTP on the local network. Pairing helps prevent casual access by other devices, but a four-digit PIN is not strong protection against determined attackers and it does not encrypt traffic or protect against someone who can monitor or alter an untrusted network. Use ClipShare only on a network you trust. Anyone with network access to the host and session access can view shared content. Your computer's firewall or network settings may need to allow local-network connections; ClipShare does not change firewall rules. Guest Wi-Fi isolation may prevent devices from reaching each other.

Messages are held in memory. Uploaded files are held in temporary storage outside the installation directory. **Stopping or quitting ClipShare deletes the messages and uploaded files for that session.** In-progress uploads are temporary too. The application does not make a permanent archive.

The host listens for LAN connections while sharing is on. Stop sharing to close the listener. If port 3570 is already in use, ClipShare selects an available port and shows the actual address in its control window.

## Uninstall

- **Windows:** use Windows Settings → Apps → Installed apps → ClipShare, or its Start-menu uninstall entry.
- **macOS:** quit ClipShare, then move ClipShare from Applications to the Trash.
- **Debian/Ubuntu:** remove ClipShare using the graphical package manager.
- **Fedora:** remove ClipShare using the graphical package manager.

Uninstalling removes the installed application. Active session content is removed when ClipShare stops; there is no saved user library to delete.

Windows may show a SmartScreen prompt if an installer is unsigned. macOS may block an unsigned or unnotarized package; public macOS releases require the project owner to configure Apple Developer ID signing and notarization. Linux may request administrator approval to install or remove a system package. These operating-system prompts depend on release signing and package-manager policy.

## Troubleshooting

- If the page does not open, choose **Open ClipShare** in the control window and use the local address shown there.
- If another device cannot connect, confirm both devices are on the same reachable network, use the displayed LAN address and current session code, and check host firewall or guest-network isolation settings.
- If the LAN address is unavailable, connect the host to a network and restart sharing.
- If the session code does not work, check that sharing is still on and use the code for the current session. Stop/Start creates a new code.
- If you need to end access immediately, choose **Stop sharing**. The server closes and temporary content is deleted.

## Developers

See [the development and release guide](docs/development.md) for architecture, local tests, native build commands, CI, signing secrets, and platform validation status. The [architecture plan](docs/architecture-and-porting-plan.md) records product and security decisions.
