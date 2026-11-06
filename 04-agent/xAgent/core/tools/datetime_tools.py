"""日期与闰年工具：通过本地系统命令获取时间，不重复实现系统逻辑。"""

from __future__ import annotations

import subprocess

from core.tools.base import Tool


def _run_command(command: str) -> str:
    """执行本地命令并返回输出文本（自动兼容 UTF-8 / GBK 编码）。"""
    raw = subprocess.run(command, shell=True, capture_output=True).stdout
    for encoding in ("utf-8", "gbk"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore").strip()


def get_date() -> str:
    date_text = _run_command("date /t")
    time_text = _run_command("time /t")
    return f"当前日期：{date_text}，当前时间：{time_text}"


def is_leap_year(year: int) -> str:
    year = int(year)
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return f"{year} 年是闰年。"
    return f"{year} 年不是闰年（平年）。"


def build_datetime_tools() -> list[Tool]:
    return [
        Tool(
            name="getDate",
            description="获取当前电脑的日期和时间。当用户询问今天几号、现在几点、当前日期或时间时调用。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=get_date,
        ),
        Tool(
            name="isLeapYear",
            description="判断某一年是否为闰年。当用户询问某一年是不是闰年时调用。",
            parameters={
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2024。"}
                },
                "required": ["year"],
            },
            handler=is_leap_year,
        ),
    ]
