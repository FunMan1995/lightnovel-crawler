#!/usr/bin/env python3

import os
import sys

# For executable bundles
if not __package__ and not hasattr(sys, "frozen"):
    path = os.path.realpath(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(path)))

    try:
        import multiprocessing

        multiprocessing.freeze_support()
    except Exception:
        pass

# For encoding
try:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
except Exception:
    pass


# Remove colors from terminal in CI
if os.getenv("CI"):
    os.environ["TERM"] = "dumb"
    os.environ["NO_COLOR"] = "1"


def main():
    if os.environ.get("LNCRAWL_PYLSP") == "1":
        # Start pylsp server
        from pylsp import __main__ as _pylsp_main

        _pylsp_main.main()
    else:
        # Start main app
        from .app import app

        app()


if __name__ == "__main__":
    main()
