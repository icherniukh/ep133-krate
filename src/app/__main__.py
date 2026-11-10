"""Briefcase iOS bootstrap — delegates to app.app."""

import os

# iOS sandbox has limited locale support. Skip setlocale entirely to avoid crash.
# Setting LC_ALL/LANG to C keeps downstream startup code (e.g. Toga) on a safe
# portable locale without invoking the unsupported locale database.
os.environ.setdefault("LC_ALL", "C")
os.environ.setdefault("LANG", "C")

from app.app import main

if __name__ == '__main__':
    main().main_loop()