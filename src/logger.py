import logging
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)

    env_level = os.environ.get("CPA_LOG_LEVEL", "DEBUG").upper()
    file_level = _LOG_LEVELS.get(env_level, logging.DEBUG)
    console_level = max(file_level, logging.INFO)

    _logger = logging.getLogger("construction_project")
    _logger.setLevel(logging.DEBUG)
    _logger.handlers.clear()

    fh = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
    fh.setLevel(file_level)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(console_level)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    ))

    _logger.addHandler(fh)
    _logger.addHandler(ch)

    return _logger


logger = setup_logger()