import logging
import sys
from typing import Optional

COLORS = {
    "DEBUG": "\033[94m",  # Blue
    "INFO": "\033[92m",  # Green
    "WARNING": "\033[93m",  # Yellow
    "ERROR": "\033[91m",  # Red
    "CRITICAL": "\033[95m",  # Magenta
    "ENDC": "\033[0m",  # Reset color
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""

    def format(self, record):
        levelname = record.levelname
        if levelname in COLORS:
            record.levelname = f"{COLORS[levelname]}{levelname}{COLORS['ENDC']}"
        return super().format(record)


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Set up and return a logger with colored console output.

    Args:
        name: The name of the logger (typically __name__)
        level: The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
              If None, defaults to INFO

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)

    log_level = getattr(logging, level.upper()) if level else logging.INFO
    logger.setLevel(log_level)

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        formatter = ColoredFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
