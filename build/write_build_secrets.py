"""Write mico360/_build_secrets.py — the System AI key built into the app.

The key never goes into the (public) source code. The build reads it from:
  1. the MICO360_SYSTEM_AI_KEY environment variable (the macOS build gets it
     from the repository secret of the same name), or
  2. build/system_ai.key — a one-line text file on the build PC
     (git-ignored, like mico360/_build_secrets.py itself).
With neither, the app is built without a key and the System AI asks for one.
The key itself is never printed.

Run:  python build/write_build_secrets.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
KEY_FILE = ROOT / "build" / "system_ai.key"
OUT = ROOT / "mico360" / "_build_secrets.py"


def write(out: Path = OUT, key_file: Path = KEY_FILE) -> str:
    """Write the secrets module; returns where the key came from ("" if none).
    Always rewrites it, so a key from an earlier build can't linger."""
    from mico360.core.ai import sanitize_key, scramble_key
    key = sanitize_key(os.environ.get("MICO360_SYSTEM_AI_KEY", ""))
    source = "MICO360_SYSTEM_AI_KEY" if key else ""
    if not key and key_file.exists():
        key = sanitize_key(key_file.read_text(encoding="utf-8"))
        source = key_file.name if key else ""
    out.write_text(
        '"""Written by build/write_build_secrets.py at build time — not in git."""\n'
        f'SYSTEM_AI_KEY = "{scramble_key(key) if key else ""}"\n', encoding="utf-8")
    return source


def main() -> int:
    source = write()
    if source:
        print(f"System AI key built in (from {source}).")
    else:
        print("WARNING: no System AI key (set MICO360_SYSTEM_AI_KEY or create "
              "build/system_ai.key) - users will have to paste one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
