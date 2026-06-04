"""Single-instance guard.

Only one copy of the app may run per user. A second launch detects the first,
asks it to come to the foreground, shows a friendly "already running" message,
and exits — instead of opening a duplicate window.

Built on Qt's local socket (a Windows named pipe under the hood), so it survives
sleep / hibernation as long as the first instance is alive, and cleans itself up
automatically when that instance exits or crashes (the OS releases the pipe).
"""
from __future__ import annotations

import getpass
import hashlib

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_ACTIVATE = b"ACTIVATE\n"
_CONNECT_TIMEOUT_MS = 400


def _default_name() -> str:
    """A stable, per-user pipe name (so different users on the same PC each get
    their own instance, but a user can't launch two of their own)."""
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    digest = hashlib.sha1(f"MICO360DocToolkit::{user}".encode("utf-8")).hexdigest()[:16]
    return f"MICO360DocToolkit-{digest}"


class SingleInstance(QObject):
    """Detect/claim the single-instance slot.

    Construct it right after the QApplication. If :meth:`is_primary` is False,
    call :meth:`signal_running` and exit. If it's True, connect :attr:`activated`
    to a slot that raises your main window.
    """

    activated = Signal()   # emitted in the primary when a second launch occurs

    def __init__(self, name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._name = name or _default_name()
        self._server: QLocalServer | None = None
        self._primary = False
        self._claim()

    # -- detection / claim -------------------------------------------------
    def _claim(self) -> None:
        # If we can connect, another instance already owns the slot.
        probe = QLocalSocket()
        probe.connectToServer(self._name)
        if probe.waitForConnected(_CONNECT_TIMEOUT_MS):
            probe.abort()
            self._primary = False
            return
        probe.abort()
        # Nobody home — become the primary. removeServer() clears a stale socket
        # left by a previous crash (a no-op for live named pipes on Windows).
        QLocalServer.removeServer(self._name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._primary = bool(self._server.listen(self._name))

    def is_primary(self) -> bool:
        return self._primary

    def is_running(self) -> bool:
        """True if another instance is already running (i.e. we are not primary)."""
        return not self._primary

    # -- second instance -> ping the primary -------------------------------
    def signal_running(self) -> bool:
        """Tell the already-running instance to come to the front. Returns True
        if the ping was delivered."""
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if not sock.waitForConnected(_CONNECT_TIMEOUT_MS):
            return False
        try:
            sock.write(_ACTIVATE)
            sock.flush()
            sock.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
            sock.disconnectFromServer()
        except Exception:
            return False
        return True

    # -- primary side: incoming ping ---------------------------------------
    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return

        def _handle() -> None:
            try:
                conn.readAll()
            except Exception:
                pass
            self.activated.emit()
            conn.disconnectFromServer()

        conn.readyRead.connect(_handle)
        # If the peer disconnects before we read (very fast), still activate.
        conn.disconnected.connect(self.activated.emit)

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
