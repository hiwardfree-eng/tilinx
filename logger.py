import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from config import LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(name: str = "tilinx") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Consola
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Archivo rotativo (10 MB, 5 backups)
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "tilinx.log"),
        maxBytes=10_485_760,
        backupCount=5,
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger

log = setup_logger()
