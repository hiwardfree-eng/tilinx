import os
import sys
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
LOG_DIR = os.environ.get("TilinX_LOG_DIR", str(BASE_DIR / "logs"))
DATA_DIR = os.environ.get("TilinX_DATA_DIR", str(BASE_DIR / "data" / "TilinX"))
DB_PATH = os.environ.get("TilinX_DB_PATH", str(BASE_DIR / "ips.json"))
KEYS_PATH = os.environ.get("TilinX_KEYS_PATH", str(BASE_DIR / "keys.json"))

class BaseConfig:
    BOT_TOKEN = os.environ.get("TilinX_BOT_TOKEN", "")
    ADMIN_ID = int(os.environ.get("TilinX_ADMIN_ID", "0"))
    DB_PATH = os.environ.get("TilinX_DB_PATH", str(BASE_DIR / "ips.json"))
    KEYS_PATH = os.environ.get("TilinX_KEYS_PATH", str(BASE_DIR / "keys.json"))
    PROXY_ENABLED = os.environ.get("TilinX_PROXY_ENABLED", "0") == "1"
    PROXY_URL = os.environ.get("TilinX_PROXY_URL", "")
    PROXY_TYPE = os.environ.get("TilinX_PROXY_TYPE", "socks5")
    PROXY_PORT = int(os.environ.get("TilinX_PROXY_PORT", "8884"))
    PROXY_AUTH_USER = os.environ.get("TilinX_PROXY_AUTH_USER", "TilinX")
    PROXY_AUTH_PASS = os.environ.get("TilinX_PROXY_AUTH_PASS", "TilinX")
    LOG_LEVEL = "INFO"

class DevelopmentConfig(BaseConfig):
    LOG_LEVEL = "DEBUG"
    DB_PATH = os.environ.get("TilinX_DB_PATH", str(BASE_DIR / "ips.dev.json"))
    DEBUG = True

class TestingConfig(BaseConfig):
    LOG_LEVEL = "DEBUG"
    DB_PATH = os.environ.get("TilinX_DB_PATH", str(BASE_DIR / "ips.test.json"))
    TESTING = True

class ProductionConfig(BaseConfig):
    LOG_LEVEL = "INFO"
    DEBUG = False
    TESTING = False

config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}

ENV = os.environ.get("TilinX_ENV", "production")
if ENV not in config_map:
    print(f"⚠️ Unknown env '{ENV}', falling back to production")
    ENV = "production"

Config = config_map[ENV]
