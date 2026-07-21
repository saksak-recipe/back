import asyncio
import logging

import pytest
from loguru import logger

from domains.auth.email_service import EmailService
from domains.auth.verification_store import PURPOSE_SIGNUP


def test_console_backend_logs_code(caplog: pytest.LogCaptureFixture):
    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        svc = EmailService(backend="console")
        with caplog.at_level(logging.INFO):
            asyncio.run(
                svc.send_verification_code(
                    "a@example.com", "123456", PURPOSE_SIGNUP
                )
            )
        assert "123456" in caplog.text
        assert "a@example.com" in caplog.text
    finally:
        logger.remove(handler_id)
