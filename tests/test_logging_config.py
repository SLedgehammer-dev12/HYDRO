from __future__ import annotations

import logging
import sys
import unittest
from io import StringIO

from hidrostatik_test.logging_config import (
    get_logger,
    install_exception_handler,
    log_unhandled_exception,
)


class InstallExceptionHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_excepthook = sys.excepthook

    def tearDown(self) -> None:
        sys.excepthook = self._original_excepthook

    def test_installs_log_unhandled_exception_as_excepthook(self) -> None:
        install_exception_handler()
        self.assertIs(sys.excepthook, log_unhandled_exception)

    def test_install_is_idempotent(self) -> None:
        install_exception_handler()
        first = sys.excepthook
        install_exception_handler()
        self.assertIs(sys.excepthook, first)


class GetLoggerTests(unittest.TestCase):
    def tearDown(self) -> None:
        logging.getLogger("hidrostatik_test").handlers.clear()

    def test_returns_logger_instance(self) -> None:
        logger = get_logger()
        self.assertIsInstance(logger, logging.Logger)

    def test_returns_same_logger_on_multiple_calls(self) -> None:
        logger1 = get_logger()
        logger2 = get_logger()
        self.assertIs(logger1, logger2)

    def test_logger_level_is_warning(self) -> None:
        logger = get_logger()
        self.assertEqual(logger.level, logging.WARNING)


class LogUnhandledExceptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_excepthook = sys.excepthook
        self._original_excepthook__ = sys.__excepthook__

    def tearDown(self) -> None:
        sys.excepthook = self._original_excepthook
        sys.__excepthook__ = self._original_excepthook__

    def test_keyboard_interrupt_delegates_to_system_excepthook(self) -> None:
        captured: list[tuple] = []

        def fake_hook(typ, val, tb) -> None:
            captured.append((typ, val, tb))

        sys.__excepthook__ = fake_hook
        exc = KeyboardInterrupt()

        log_unhandled_exception(type(exc), exc, None)

        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0][0], KeyboardInterrupt)

    def test_other_exceptions_are_logged_at_critical(self) -> None:
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.CRITICAL)
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

        logger = get_logger()
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.CRITICAL)

        try:
            exc = ValueError("test error")
            log_unhandled_exception(type(exc), exc, None)

            output = stream.getvalue()
            self.assertIn("CRITICAL", output)
            self.assertIn("test error", output)
        finally:
            logger.handlers.clear()


if __name__ == "__main__":
    unittest.main()
