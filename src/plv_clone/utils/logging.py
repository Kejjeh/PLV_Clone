"""Structured logging configuration for the PLV Clone pipeline."""

from __future__ import annotations

import logging
import sys
from typing import Any


_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a clean, structured formatter.

    Safe to call multiple times — only configures once.
    """
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str, **extra: Any) -> logging.Logger:
    """Return a named logger, ensuring root logging is configured."""
    configure_logging()
    return logging.getLogger(name)
