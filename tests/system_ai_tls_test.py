"""The System AI over HTTPS.

In October 2026 the System AI server got a certificate and stopped answering
plain HTTP on its port, which silently broke AI in every installed copy. These
checks pin the move to HTTPS:

* the built-in address is https://, a bare "ai.mico360.com:5310" normalises to
  https://, and the built-in key is never offered to a plain-http address;
* a key saved while the System AI was still http://… keeps working (it is
  re-bound to the HTTPS address instead of asking the user to paste it again);
* live (skipped when offline): the real server is reached over TLS with a
  certificate Python trusts, answers 401 to a dummy key the way the app
  expects, and the old plain-HTTP address no longer answers — so the app's
  https:// default is the only one that works.

Run:  python tests/system_ai_tls_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def test_offline() -> None:
    print("--- addresses ---")
    from mico360.config import settings
    from mico360.core import ai
    check("the System AI address is HTTPS", ai.SYSTEM_BASE_URL.startswith("https://"),
          ai.SYSTEM_BASE_URL)
    check("a bare System AI host normalises to https://",
          ai.normalize_base_url("ai.mico360.com:5310") == "https://ai.mico360.com:5310/v1",
          ai.normalize_base_url("ai.mico360.com:5310"))
    check("local servers still default to plain http",
          ai.normalize_base_url("localhost:11434") == "http://localhost:11434/v1"
          and ai.normalize_base_url("192.168.1.5:1234") == "http://192.168.1.5:1234/v1")
    check("the plain-http address is not treated as the System AI",
          not ai.is_system_url("http://ai.mico360.com:5310/v1")
          and ai.is_system_url(ai.SYSTEM_BASE_URL))

    print("--- a key saved before the move to HTTPS ---")
    saved = (settings.ai_api_key_sealed, settings.ai_key_origin, settings.ai_source,
             settings.ai_base_url, settings.ai_enabled)
    os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
    try:
        settings.ai_enabled = True
        settings.ai_source = ai.SOURCE_SYSTEM
        settings.ai_base_url = ""
        settings.ai_api_key_sealed = ai.seal_key("mico_old_system_key_0123456789")
        settings.ai_key_origin = "http://ai.mico360.com:5310"          # as 7.6.0 saved it
        cfg = ai.load_config()
        check("an old System AI key still works after the move",
              cfg.api_key == "mico_old_system_key_0123456789" and cfg.is_usable()[0],
              cfg.is_usable()[1])
        check("…and is re-bound to the HTTPS address",
              settings.ai_key_origin == "https://ai.mico360.com:5310", settings.ai_key_origin)
        check("it is still never sent to a different server",
              ai.stored_key_for("https://api.example.com/v1") == ""
              and ai.stored_key_for("http://127.0.0.1:11434/v1") == "")
        settings.ai_key_origin = "http://other.example.com:5310"
        check("a key saved for some other plain-http server is not moved",
              ai.load_config().api_key == ""
              and settings.ai_key_origin == "http://other.example.com:5310")
        os.environ["MICO360_SYSTEM_AI_KEY"] = "mico_builtin_key_0123456789abc"
        settings.ai_api_key_sealed = ""
        check("a built-in key goes to the HTTPS System AI only",
              ai.stored_key_for(ai.SYSTEM_BASE_URL) == "mico_builtin_key_0123456789abc"
              and ai.stored_key_for("http://ai.mico360.com:5310/v1") == "")
    finally:
        os.environ.pop("MICO360_SYSTEM_AI_KEY", None)
        (settings.ai_api_key_sealed, settings.ai_key_origin, settings.ai_source,
         settings.ai_base_url, settings.ai_enabled) = saved

    print("--- wording ---")
    from mico360 import legal
    privacy = legal.privacy_policy()
    check("Privacy no longer says the System AI is unencrypted",
          "not\nyet encrypted" not in privacy and "not yet encrypted" not in privacy
          and "encrypted in transit" in privacy)
    src = (Path(__file__).resolve().parent.parent / "mico360").rglob("*.py")
    stale = [p.name for p in src if "http://ai.mico360.com" in p.read_text(encoding="utf-8")
             and p.name != "ai.py"]
    check("no screen or hint still shows the old http:// address", not stale, str(stale))


def test_live() -> None:
    print("--- live: the real System AI server ---")
    import socket
    import urllib.error
    import urllib.request
    from mico360.core import ai
    host = "ai.mico360.com"
    try:
        socket.create_connection((host, 5310), timeout=8).close()
    except OSError as exc:
        print(f"[SKIP] {host} not reachable from here ({type(exc).__name__}) — "
              "live checks skipped")
        return
    cfg = ai.AiConfig(enabled=True, source=ai.SOURCE_SYSTEM,
                      api_key="not-a-real-key-just-probing", model=ai.SYSTEM_MODEL)
    ok, msg = ai.test_connection(cfg)
    check("the app reaches the System AI over HTTPS (certificate verified) and "
          "gets the expected 'key rejected' for a dummy key",
          not ok and "rejected" in msg.lower(), msg[:120])
    try:
        urllib.request.urlopen("http://ai.mico360.com:5310/v1/models", timeout=8)
        plain = "answered"
    except urllib.error.HTTPError as exc:
        plain = f"answered HTTP {exc.code}"
    except Exception as exc:                    # noqa: BLE001
        plain = f"no answer ({type(exc).__name__})"
    print(f"[INFO] the old plain-http address: {plain}")
    check("the HTTPS default is what actually works",
          plain.startswith("no answer") or not ok, plain)


def main() -> int:
    test_offline()
    test_live()
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("All System AI HTTPS checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
