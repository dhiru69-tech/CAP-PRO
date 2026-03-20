"""
ReconMind — scanner/utils/logger.py
Logging for scanner module.
"""

import logging
import sys
import os


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"reconmind.scanner.{name}")

    if logger.handlers:
        return logger

    debug = os.getenv("SCANNER_DEBUG", "true").lower() == "true"
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | SCANNER | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
