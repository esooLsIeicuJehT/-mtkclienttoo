"""
Logger — structured logging with Qt signal emission + file rotation.
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from PyQt5.QtCore import QObject, pyqtSignal

LOG_DIR = os.path.join(os.path.expanduser("~"), ".mtkclient2", "logs")
os.makedirs(LOG_DIR, exist_ok=True)


class QtLogHandler(logging.Handler, QObject):
    """Forwards log records to Qt signal so UI can display them."""
    log_emitted = pyqtSignal(str, str)  # (level, message)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.log_emitted.emit(record.levelname, msg)


# Singleton handler instances
_qt_handler = None
_logger = None


def get_logger(name: str = "mtkclient2") -> logging.Logger:
    global _logger, _qt_handler
    if _logger:
        return _logger

    _logger = logging.getLogger(name)
    _logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%H:%M:%S"
    )

    # File handler
    log_file = os.path.join(
        LOG_DIR,
        f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
    fh.setFormatter(fmt)
    _logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    _logger.addHandler(ch)

    # Qt handler (lazily attached)
    _qt_handler = QtLogHandler()
    _qt_handler.setFormatter(fmt)
    _logger.addHandler(_qt_handler)

    return _logger


def get_qt_handler() -> QtLogHandler:
    get_logger()  # ensure initialized
    return _qt_handler
