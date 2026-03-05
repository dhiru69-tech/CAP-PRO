"""
ReconMind Backend — utils/logger.py
Centralized logging configuration.
"""

import logging
import sys
from config import settings


def get_logger(name: str) -> logging.Logger:
    """
    Returns a configured logger for the given module name.
    
    Usage:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")
        logger.error("Something went wrong")
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    level = logging.DEBUG if settings.DEBUG else logging.INFO
    logger.setLevel(level)

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
