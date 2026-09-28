#!/usr/bin/env python
"""Development launcher for MICO360 Doc Toolkit."""
import sys
from pathlib import Path

# Allow running from a source checkout without installation. Never in the
# built app: there this folder is the bundle's library folder, and putting it
# first on sys.path makes OpenCV's loader find its own package again instead of
# its binary ("recursion is detected during loading of cv2") — that broke OCR
# and PDF -> Word in the macOS app.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from mico360.app import main

if __name__ == "__main__":
    sys.exit(main())
