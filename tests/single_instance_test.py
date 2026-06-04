"""Single-instance guard: detection + activation messaging.

Run:  python tests/single_instance_test.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360.single_instance import SingleInstance, _default_name

    name = f"MICO360-test-{os.getpid()}"

    # 1) First instance claims the slot.
    first = SingleInstance(name)
    check("first instance becomes primary", first.is_primary() and not first.is_running())

    # 2) Second instance with the same name detects the first.
    second = SingleInstance(name)
    check("second instance is blocked (already running)",
          second.is_running() and not second.is_primary())

    # 3) The second instance can ping the first, which emits 'activated'.
    fired = []
    first.activated.connect(lambda: fired.append(1))
    loop = QEventLoop()
    first.activated.connect(loop.quit)
    delivered = second.signal_running()
    check("activation ping delivered to the primary", delivered)
    QTimer.singleShot(1500, loop.quit)
    loop.exec()
    check("primary received the activation signal", len(fired) >= 1)

    # 4) Distinct names don't collide; the per-user default name is stable.
    other = SingleInstance(name + "-other")
    check("a different name is its own primary", other.is_primary())
    check("default per-user name is stable + namespaced",
          _default_name() == _default_name() and _default_name().startswith("MICO360DocToolkit-"))

    # 5) Releasing the slot lets a new instance become primary again
    #    (models the first instance exiting; the OS frees the pipe).
    first.close()
    second.close()
    other.close()
    app.processEvents()
    reclaim = SingleInstance(name)
    check("slot is reclaimable after the primary closes", reclaim.is_primary())
    reclaim.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All single-instance checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
