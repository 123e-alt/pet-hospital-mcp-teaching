"""日期与闰年工具：使用标准库 datetime，跨平台（Windows/Linux/macOS），非硬编码。"""

from __future__ import annotations

from datetime import datetime

from core.tools.base import Tool


def get_date() -> str:
    """返回当前日期时间（本地时区，跨平台一致）。"""
    now = datetime.now().astimezone()
    week = "一二三四五六日"[now.weekday()]
    return (
        f"当前日期：{now:%Y-%m-%d}（星期{week}），"
        f"当前时间：{now:%H:%M:%S}，时区：{now:%z or '本地'}"
    )


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
