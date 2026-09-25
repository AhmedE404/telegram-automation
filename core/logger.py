"""
Centralised logging setup.
Import `get_logger` wherever you need logging — never configure logging
in module-level code outside of this file.

Usage:
    from core.logger import get_logger
    logger = get_logger(__name__)
"""

import logging
import sys


def _configure_root() -> None:
    """Configure root logger once at import time."""
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    if not root.handlers:          # guard against double-setup
        root.addHandler(handler)
        root.setLevel(logging.INFO)


_configure_root()


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (child of root)."""
    return logging.getLogger(name)
