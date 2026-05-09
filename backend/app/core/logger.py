"""Centralised logger using loguru."""

import sys

from loguru import logger

from app.config import get_settings

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level="DEBUG" if settings.debug else "INFO",
        backtrace=settings.debug,
        diagnose=settings.debug,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    _configured = True


__all__ = ["logger", "setup_logging"]
