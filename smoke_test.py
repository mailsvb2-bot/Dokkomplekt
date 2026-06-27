"""Backward-compatible smoke entrypoint."""

from __future__ import annotations

import os
import sys

from smoke_combined_runner import run


if __name__ == "__main__":
    run()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
