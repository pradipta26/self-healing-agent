from datetime import datetime, timezone
import logging


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a shared logger instance with a standard format."""
    logger_name = name or "self_healing_agent"
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger
