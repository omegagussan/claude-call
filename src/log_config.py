import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def configure_logging() -> None:
    """Configure application output independently of the server launcher."""
    logger = logging.getLogger("src")
    if any(handler.get_name() == "application-json" for handler in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name("application-json")
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "default": {
            "formatter": "json",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
        "access": {
            "formatter": "json",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        "src": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}
