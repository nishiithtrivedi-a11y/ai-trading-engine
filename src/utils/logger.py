"""
Logging configuration for the backtesting engine.

Provides a consistent logger setup with both console and optional file output.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "backtest",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Create and configure a logger.

    Args:
        name: Logger name.
        level: Logging level.
        log_file: Optional file path for log output.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(file_path))
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Module-level default logger
logger = setup_logger()
