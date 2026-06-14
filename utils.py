from typing import Union
from datetime import datetime


def format_date(ts: Union[float, int, None]) -> str:
    if not ts or ts == 0:
        return "\u2014"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def parse_duration(text: str) -> int:
    text = text.strip().lower()
    try:
        if text.endswith("m"):
            return int(text[:-1]) * 60
        if text.endswith("h"):
            return int(text[:-1]) * 3600
        if text.endswith("d"):
            return int(text[:-1]) * 86400
        return int(text) * 3600
    except ValueError:
        raise ValueError("Invalid duration format. Use: 30m / 6h / 14d")
