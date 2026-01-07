# config.py
import os
import logging
from logging.handlers import RotatingFileHandler

# =========================
# BASIC PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE_PATH = os.path.join(LOG_DIR, "bot.log")

# =========================
# TELEGRAM CREDENTIALS
# =========================
APP_ID = int(os.getenv("API_ID", "25331263"))
API_HASH = os.getenv("API_HASH", "cab85305bf85125a2ac053210bcd1030")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")

# =========================
# BOT SETTINGS
# =========================
BOT_WORKERS = int(os.getenv("BOT_WORKERS", "8"))
OWNER_ID = int(os.getenv("OWNER_ID", "1955406483"))
ADMINS = list(map(int, os.getenv("ADMINS", str(OWNER_ID)).split()))

# =========================
# DATABASE SETTINGS
# =========================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "MediaBotDB")

# =========================
# CHANNEL SETTINGS
# =========================
FORCE_SUB_CHANNEL = int(os.getenv("FORCE_SUB_CHANNEL", "0"))
DUMP_ID = int(os.getenv("DUMP_ID", "0"))

# =========================
# PREMIUM SETTINGS
# =========================
PREMIUM_COOLDOWN = 1500  # 25 minutes in seconds
PREMIUM_USERS = list(map(int, os.getenv("PREMIUM_USERS", "").split())) if os.getenv("PREMIUM_USERS") else []

# =========================
# WEB SERVER
# =========================
PORT = int(os.getenv("PORT", "8000"))

# =========================
# FILE SIZE LIMITS (in bytes)
# =========================
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
NON_PREMIUM_MAX_SIZE = 500 * 1024 * 1024  # 500MB for non-premium

# =========================
# LOGGING SETUP
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)

def LOGGER(name: str):
    return logging.getLogger(name)
