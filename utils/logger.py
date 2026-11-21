"""共用日誌工具（支援彩色終端輸出、檔案輪替與環境變數設定）。"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_LOGGER_NAME = "corn_agent"
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG: "\033[36m",  # Cyan
    logging.INFO: "\033[32m",  # Green
    logging.WARNING: "\033[33m",  # Yellow
    logging.ERROR: "\033[31m",  # Red
    logging.CRITICAL: "\033[1;31m",  # Bold Red
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """為終端輸出的日誌等級加上 ANSI 顏色。"""

    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, "")
        original_levelname = record.levelname
        if color:
            record.levelname = f"{color}{original_levelname:<8}{_RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


def _resolve_level(level: str | int | None) -> int:
    """將等級名稱或數字轉換為 logging 等級常數。"""
    if isinstance(level, int):
        return level
    raw = (level or os.getenv("LOG_LEVEL", "INFO")).strip().upper()
    resolved = getattr(logging, raw, None)
    if not isinstance(resolved, int):
        raise ValueError(f"無效的日誌等級：{raw!r}")
    return resolved


def _should_use_color(color: bool | None) -> bool:
    """決定終端輸出是否啟用顏色。"""
    if color is not None:
        return color
    if os.getenv("NO_COLOR") is not None:
        return False
    env_color = os.getenv("LOG_COLOR")
    if env_color is not None:
        return env_color.strip().lower() not in {"0", "false", "no", "off"}
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _has_stream_handler(log: logging.Logger) -> bool:
    return any(type(h) is logging.StreamHandler for h in log.handlers)


def _has_file_handler(log: logging.Logger, target_path: Path) -> bool:
    resolved = target_path.resolve()
    for handler in log.handlers:
        if isinstance(handler, logging.FileHandler):
            if Path(handler.baseFilename).resolve() == resolved:
                return True
    return False


def get_logger(
    name: str | None = None,
    *,
    level: str | int | None = None,
    log_file: str | Path | None = None,
    color: bool | None = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """取得設定完成的 Logger 實例。

    Args:
        name: Logger 名稱（建議傳入 ``__name__``），預設為 ``"corn_agent"``。
        level: 日誌等級（如 ``"DEBUG"``、``logging.INFO``），預設讀取環境變數 ``LOG_LEVEL``（預設 ``INFO``）。
        log_file: 選填的日誌檔案路徑，未指定時會讀取環境變數 ``LOG_FILE``。
        color: 是否在終端顯示彩色等級標籤，預設依終端環境與 ``LOG_COLOR`` / ``NO_COLOR`` 自動判斷。
        max_bytes: 單一日誌檔案大小上限（bytes），預設 5 MB。
        backup_count: 輪替保留的舊日誌檔案數量，預設 3。

    Returns:
        已設定完成的 ``logging.Logger`` 實例。
    """
    logger_name = name or DEFAULT_LOGGER_NAME
    log = logging.getLogger(logger_name)
    resolved_level = _resolve_level(level)
    log.setLevel(resolved_level)
    log.propagate = False

    if not _has_stream_handler(log):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(resolved_level)
        if _should_use_color(color):
            stream_fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            stream_handler.setFormatter(
                _ColorFormatter(stream_fmt, datefmt=DEFAULT_DATE_FORMAT)
            )
        else:
            stream_handler.setFormatter(
                logging.Formatter(DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT)
            )
        log.addHandler(stream_handler)
    elif level is not None:
        for handler in log.handlers:
            handler.setLevel(resolved_level)

    resolved_file = log_file or os.getenv("LOG_FILE")
    if resolved_file:
        file_path = Path(resolved_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not _has_file_handler(log, file_path):
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(resolved_level)
            file_handler.setFormatter(
                logging.Formatter(DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT)
            )
            log.addHandler(file_handler)

    return log


# 預設共用的 Logger 實例，可直接 `from utils.logger import logger` 使用
logger = get_logger()
