#!/usr/bin/env python3
"""appforge CLI entry point. Requires Python 3.10+ and PyYAML (pip install pyyaml)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from appforge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
