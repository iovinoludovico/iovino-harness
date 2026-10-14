#!/usr/bin/env python3
"""modeler CLI entry point (Python 3.10+; PyYAML if installed, else the vendored copy)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metamodel.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
