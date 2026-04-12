"""Application logging helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_NAME = "master_sentinal"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a configured application logger."""
    logger_name = _LOG_NAME if not name else f"{_LOG_NAME}.{name}"
    logger = logging.getLogger(logger_name)
    root = logging.getLogger(_LOG_NAME)
    if not root.handlers:
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "master_sentinal.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        root.propagate = False
    return logger
