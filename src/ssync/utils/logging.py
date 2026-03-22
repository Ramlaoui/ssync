import logging
import sys
from collections import deque
from threading import Lock
from typing import List, Optional

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


class MemoryLogHandler(logging.Handler):
    """Handler that stores log records in memory for API access."""

    def __init__(self, max_entries: int = 1000):
        super().__init__()
        self.max_entries = max_entries
        self._logs: deque = deque(maxlen=max_entries)
        self._lock = Lock()
        self.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._lock:
                self._logs.append(msg)
        except Exception:
            self.handleError(record)

    def get_logs(self, lines: int = 50) -> List[str]:
        """Get the most recent log entries."""
        with self._lock:
            logs = list(self._logs)
        return logs[-lines:] if lines < len(logs) else logs

    def clear(self) -> None:
        """Clear all stored logs."""
        with self._lock:
            self._logs.clear()


# Global memory log handler instance
_memory_handler: Optional[MemoryLogHandler] = None


def get_memory_handler() -> MemoryLogHandler:
    """Get or create the global memory log handler."""
    global _memory_handler
    if _memory_handler is None:
        _memory_handler = MemoryLogHandler()
    return _memory_handler


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a named logger. Handlers are configured once via configure_logging()."""
    return logging.getLogger(name)


def configure_logging(level: Optional[str] = None, memory: bool = False) -> None:
    """Set up ssync logging. Call once at application startup.

    Attaches a console handler to the top-level 'ssync' logger with
    propagate=False so all ssync.* child loggers share one handler without
    leaking records to the root logger (e.g. uvicorn's handler).
    """
    ssync_logger = logging.getLogger("ssync")
    log_level = getattr(logging, level.upper()) if level else logging.INFO
    ssync_logger.setLevel(log_level)
    ssync_logger.propagate = False

    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, MemoryLogHandler)
        for h in ssync_logger.handlers
    )
    if not has_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(
            ColoredFormatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        ssync_logger.addHandler(console_handler)

    if memory:
        enable_memory_logging(level)


def enable_memory_logging(level: Optional[str] = None) -> None:
    """Attach the memory handler to the ssync logger for API log access."""
    memory_handler = get_memory_handler()
    log_level = getattr(logging, level.upper()) if level else logging.INFO
    memory_handler.setLevel(log_level)

    ssync_logger = logging.getLogger("ssync")
    if memory_handler not in ssync_logger.handlers:
        ssync_logger.addHandler(memory_handler)
