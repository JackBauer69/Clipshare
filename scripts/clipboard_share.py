#!/usr/bin/env python3
"""Launch ClipShare directly from a source checkout."""

from pathlib import Path
import runpy


APPLICATION = Path(__file__).resolve().parents[1] / "src/clipshare/clipboard_share.py"
runpy.run_path(str(APPLICATION), run_name="__main__")
