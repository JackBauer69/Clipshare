"""Application command entry point used by native packaging and developers."""

import sys

from . import __version__


def self_test():
    import tkinter

    from urllib.request import urlopen

    from .clipboard_share import ShareServer

    # This exercises the bundled Tcl runtime without needing to open a GUI window.
    tkinter.Tcl()
    session = ShareServer(host="127.0.0.1", port=0).start()
    try:
        with urlopen(f"http://127.0.0.1:{session.port}/", timeout=5) as response:
            if response.status != 200 or b"Join ClipShare" not in response.read():
                raise RuntimeError("The ClipShare HTTP self-test did not receive the pairing page.")
    finally:
        session.stop()


def main():
    arguments = sys.argv[1:]
    if arguments == ["--version"]:
        print(__version__)
        return 0
    if arguments == ["--self-test"]:
        self_test()
        return 0

    from .desktop import main as desktop_main

    desktop_main()
    return 0
