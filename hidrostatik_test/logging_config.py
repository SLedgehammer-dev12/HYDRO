from __future__ import annotations

import logging
import sys
from pathlib import Path

_logger: logging.Logger | None = None


def get_logger(name: str = "hidrostatik_test") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    _logger = _setup_logger(name)
    return _logger


def _setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.WARNING)
    logger.handlers.clear()

    try:
        log_dir = Path.home() / "AppData" / "Local" / "HidrostatikTest" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / "app.log",
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)
    except OSError:
        pass

    return logger


def log_unhandled_exception(exc_type: type[BaseException], exc_value: BaseException, exc_tb: object) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger = get_logger()
    logger.critical("Beklenmeyen hata", exc_info=(exc_type, exc_value, exc_tb))


def install_exception_handler() -> None:
    sys.excepthook = log_unhandled_exception
