#!/usr/bin/env python3
"""Launch ClipShare directly from a source checkout."""

from pathlib import Path
import sys


SOURCE = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE))

from clipshare.launcher import main


if __name__ == "__main__":
    main()
