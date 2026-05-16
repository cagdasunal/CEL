"""Module entry point: `python3 -m tools.summary <subcommand> [--dry-run]`."""
from __future__ import annotations

import sys

from tools.summary.cli import main

if __name__ == "__main__":
    sys.exit(main())
