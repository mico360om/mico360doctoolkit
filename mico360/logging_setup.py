"""Application logging: rotating file handler + an in-memory Qt signal bridge."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QObject, Signal

from mico360.paths import logs_dir

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s"


class QtLogBridge(QObject, logging.Handler):
    """A logging handler that re-emits records as a Qt signal for the UI."""

    record = Signal(str, str)  # (levelname, formatted message)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:  # noqa: N802 (Qt naming)
        try:
            msg = self.format(record)
            self.record.emit(record.levelname, msg)
        except Exception:  # never let logging crash the app
            pass


bridge = QtLogBridge()


def setup_logging() -> logging.Logger:
    root = logging.getLogger("mico360")
    if root.handlers:  # already configured
        return root
    root.setLevel(logging.DEBUG)

    log_file = logs_dir() / "mico360.log"
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(fh)

    bridge.setLevel(logging.INFO)
    root.addHandler(bridge)

    root.propagate = False
    return root


def get_logger(name: str = "mico360") -> logging.Logger:
    return logging.getLogger(name)
