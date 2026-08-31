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
# The primary reads and closes the connection; give it a moment to do so.
_WRITE_TIMEOUT_MS = 2000


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

    # Emitted in the primary when a second launch occurs. Carries an optional
    # payload string (e.g. a JSON "open this tool with this file" request from a
    # right-click menu); an empty string means "just come to the front".
    activated = Signal(str)

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
    def signal_running(self, payload: str = "") -> bool:
        """Tell the already-running instance to come to the front, optionally
        forwarding a request payload (e.g. an "open tool with file" request).
        Returns True if the ping was delivered."""
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if not sock.waitForConnected(_CONNECT_TIMEOUT_MS):
            return False
        try:
            msg = (payload.encode("utf-8") + b"\n") if payload else _ACTIVATE
            sock.write(msg)
            sock.flush()
            sock.waitForBytesWritten(_WRITE_TIMEOUT_MS)
            # Do NOT close from this side. Wait for the PRIMARY to read the
            # message and close the connection: an abrupt sender-side close on a
            # Windows named pipe can transition the receiver straight to
            # "disconnected" (buffer cleared) so its readyRead never fires and
            # the payload is lost. Letting the primary close avoids that race.
            if not sock.waitForDisconnected(_WRITE_TIMEOUT_MS):
                sock.abort()
        except Exception:
            return False
        return True

    # -- primary side: incoming ping ---------------------------------------
    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        buf = {"data": b"", "done": False}

        def _finish() -> None:
            # Emit exactly once, from the fully-received (newline-terminated)
            # message. Reading on *disconnect* too means a payload is never lost
            # when the sender disconnects immediately after writing.
            if buf["done"]:
                return
            buf["done"] = True
            text = buf["data"].decode("utf-8", "replace").strip()
            payload = "" if text in ("", "ACTIVATE") else text
            self.activated.emit(payload)
            try:
                conn.disconnectFromServer()
            except Exception:
                pass

        def _drain() -> None:
            try:
                buf["data"] += bytes(conn.readAll().data())
            except Exception:
                pass
            if b"\n" in buf["data"]:
                _finish()

        conn.readyRead.connect(_drain)
        # On disconnect, drain any remaining bytes then finish (covers a bare
        # probe/activation that carried no newline).
        conn.disconnected.connect(lambda: (_drain(), _finish()))

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
