"""On-disk log so a hidden Windows launch still shows failures."""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from battlebuddy.memory.store import default_home

LOG_NAME = "battlebuddy.log"
_LOGGER = "battlebuddy"
_MAX_BYTES = 512_000
_BACKUPS = 2


class _FlushRotatingFileHandler(RotatingFileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def log_file(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / LOG_NAME


def setup_logging(home: Path | None = None) -> Path:
    """Line-buffer stdio. Rotate ~/.battlebuddy/battlebuddy.log."""
    path = log_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    logger = logging.getLogger(_LOGGER)
    logger.setLevel(logging.INFO)
    wanted = str(path.resolve())
    for handler in logger.handlers:
        if getattr(handler, "_battlebuddy_path", None) == wanted:
            return path
    handler = _FlushRotatingFileHandler(
        path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUPS,
        encoding="utf-8",
    )
    handler._battlebuddy_path = wanted  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.info("Battle Buddy log open. %s", path)
    return path


def report(message: str, exc: BaseException | None = None) -> None:
    """Write a line, and a traceback when exc is set. Always flush."""
    try:
        setup_logging()
    except Exception:
        pass
    logger = logging.getLogger(_LOGGER)
    if exc is not None:
        logger.error("%s\n%s", message, "".join(traceback.format_exception(exc)))
    else:
        logger.info("%s", message)
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            continue
