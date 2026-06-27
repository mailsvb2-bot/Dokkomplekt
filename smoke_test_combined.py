"""Stable entrypoint for the combined smoke suite.

Regression contract kept here for release_check:
Number popup must not open from the sick-leave Yes button.
"""

from __future__ import annotations

import os
import sys

from smoke_combined_runner import run


if __name__ == "__main__":
    run()
    # Some Tk/OS helper probes can leave a non-daemon background handle on a
    # subset of platforms after all assertions printed OK.  The smoke entrypoint
    # is a disposable process, so exit hard after a successful run instead of
    # letting release_check hang on a finished suite.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
