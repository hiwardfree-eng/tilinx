import logging
import os
import sys
import json
import traceback
from logging.handlers import RotatingFileHandler
from config import LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)

_USE_JSON = os.environ.get("TilinX_JSON_LOG", "0") == "1"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            obj["exception"] = "".join(traceback.format_exception(*record.exc_info))
        if hasattr(record, "extra"):
            obj["extra"] = record.extra
        return json.dumps(obj, ensure_ascii=False)


def setup_logger(name: str = "tilinx") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if _USE_JSON:
        fmt = JsonFormatter()
    else:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "tilinx.log"),
        maxBytes=10_485_760,
        backupCount=5,
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger

log = setup_logger()
