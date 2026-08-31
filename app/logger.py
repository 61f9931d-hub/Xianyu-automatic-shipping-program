"""日志模块：文件日志 + 通过回调/信号推送到 UI。"""
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import config

_handlers_ready = False


def _setup_file_logger() -> logging.Logger:
    global _handlers_ready
    logger = logging.getLogger("xianyu")
    logger.setLevel(logging.INFO)
    if _handlers_ready:
        return logger
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    fh = logging.FileHandler(config.LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    _handlers_ready = True
    return logger


_file_logger = _setup_file_logger()

# UI 日志回调（由 GUI 设置，接收纯文本行）
_ui_callback = None


def set_ui_callback(fn) -> None:
    global _ui_callback
    _ui_callback = fn


def _emit(msg: str, level: str = "INFO") -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} [{level}] {msg}"
    try:
        if _ui_callback:
            _ui_callback(line)
    except Exception:
        pass
    try:
        if level == "ERROR":
            _file_logger.error(msg)
        elif level == "WARN":
            _file_logger.warning(msg)
        else:
            _file_logger.info(msg)
    except Exception:
        pass


def info(msg: str) -> None:
    _emit(msg, "INFO")


def warn(msg: str) -> None:
    _emit(msg, "WARN")


def error(msg: str) -> None:
    _emit(msg, "ERROR")


def success(msg: str) -> None:
    _emit(msg, "OK")


def log_file_path() -> Path:
    return config.LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"


def exception_hook(exc_type, exc, tb):
    import traceback
    error("未捕获异常: " + "".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = exception_hook
