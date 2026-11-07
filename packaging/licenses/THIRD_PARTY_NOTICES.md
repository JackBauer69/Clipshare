# Third-party software notices

The packaged desktop app includes the Python runtime, Tcl/Tk (through Tkinter), and the PyInstaller bootloader. Their license texts are shipped in the `third_party_licenses` directory beside the executable, or in the app bundle's `Contents/Resources/third_party_licenses` directory.

- Python: PSF License, with additional notices included by the Python distribution.
- Tcl and Tk: Tcl/Tk License Terms (BSD-style).
- PyInstaller bootloader: GPLv2-or-later with the PyInstaller bootloader exception for distributing applications.

Build tools NSIS, `dpkg-deb`, and `rpmbuild` are not included in the installed application. The ClipShare source itself has no license grant in this repository yet. The owner must select and add a source license before publishing the source or making a public source-code release; no license is assumed here.

Upstream license references: [Python](https://docs.python.org/3/license.html), [Tcl/Tk](https://www.tcl-lang.org/software/tcltk/license.html), and [PyInstaller](https://pyinstaller.org/en/stable/license.html).
