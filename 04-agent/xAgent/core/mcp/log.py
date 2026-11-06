"""MCP 客户端日志：统一的 logger + 可选的滚动文件输出。

日志文件默认落在 ``<项目>/logs/mcp.log``，用于事后排查连接中断、
握手失败、重连等异常，不影响 TUI 显示。
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "xagent.mcp"

_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure(log_dir: Path, *, level: int = logging.DEBUG) -> None:
    """挂上滚动文件 handler（幂等）。目录不可写时静默降级为只写内存日志。"""
    logger = get_logger()
    logger.setLevel(level)
    if logger.handlers:  # 已配置过
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "mcp.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        return
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    # 不向上冒泡到 root，避免污染 Textual 的终端输出
    logger.propagate = False
