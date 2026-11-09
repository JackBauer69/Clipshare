# Third-party software notices

The packaged desktop app includes the Python runtime, Tcl/Tk (through Tkinter), and the PyInstaller bootloader. Their license texts are shipped in the `third_party_licenses` directory beside the executable, or in the app bundle's `Contents/Resources/third_party_licenses` directory.

- Python: PSF License, with additional notices included by the Python distribution.
- Tcl and Tk: Tcl/Tk License Terms (BSD-style).
- PyInstaller bootloader: GPLv2-or-later with the PyInstaller bootloader exception for distributing applications.

Build tools NSIS, `dpkg-deb`, and `rpmbuild` are not included in the installed application. The ClipShare source itself has no license grant in this repository yet. The owner must select and add a source license before publishing the source or making a public source-code release; no license is assumed here.

Upstream license references: [Python](https://docs.python.org/3/license.html), [Tcl/Tk](https://www.tcl-lang.org/software/tcltk/license.html), and [PyInstaller](https://pyinstaller.org/en/stable/license.html).

## Versioned license sources used by the build

The build copies the Python license included with the Python installation when one is present. For Python 3.12 CI environments without an on-disk license, it uses the full upstream CPython 3.12.10 license text checked in at `packaging/licenses/upstream/Python-3.12.10-LICENSE.txt` ([CPython v3.12.10 LICENSE](https://github.com/python/cpython/blob/v3.12.10/LICENSE)). This fallback is limited to Python 3.12; other Python versions must supply an installed license.

For Tcl/Tk 8.6, the build uses distinct original license texts in `packaging/licenses/upstream/`: [Tcl 8.6 license.terms](https://github.com/tcltk/tcl/blob/core-8-6-branch/license.terms) and [Tk 8.6 license.terms](https://github.com/tcltk/tk/blob/core-8-6-branch/license.terms). Both are from the respective official 8.6 source branches. They are included verbatim. Other Tcl/Tk versions are rejected pending review of their own license terms.

PyInstaller's license notices continue to be collected from the installed PyInstaller distribution. The build intentionally fails if required notices cannot be located.
