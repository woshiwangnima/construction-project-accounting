import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from .paths import get_log_dir

LOG_DIR = str(get_log_dir())
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

    fh = RotatingFileHandler(
        LOG_FILE,
        encoding="utf-8",
        mode="a",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
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


# 惰性初始化：导入本模块不创建 logs 目录，也不绑定 handler。
# GUI 入口（main.py）显式调用 setup_logger() 完成配置。
logger = logging.getLogger("construction_project")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())
