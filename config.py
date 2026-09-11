import os
import re

def get_config(key, default):
    """Get environment variable or fallback to default if missing or empty."""
    val = os.getenv(key)
    if val and val.strip():
        return val
    return default

# Telegram Bot Configuration
# 1. Preferred: Set environment variables (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
# 2. Fallback: Paste your values between the quotes below if Option 1 fails
TELEGRAM_BOT_TOKEN = get_config("TELEGRAM_BOT_TOKEN", "8306899550:AAF--2j7HyZV_pMBKvfFAK_v9eSAcy5DbiQ")

def parse_chat_id(val):
    if not val: return val
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return val

TELEGRAM_CHAT_ID = parse_chat_id(get_config("TELEGRAM_CHAT_ID", "-1003830805941"))
AFFILIATE_TAG = get_config("AFFILIATE_TAG", "unboxvibes03-21")
UTM_TAG = get_config("UTM_TAG", "unboxvibes-telegram-21")
BRIDGE_URL = get_config("BRIDGE_URL", "https://amazon-deal-bridge.hakimkhan01h2.workers.dev")
ENABLE_BRIDGE = str(get_config("ENABLE_BRIDGE", "1")).strip().lower() in ("1", "true", "yes", "on")

# Amazon API disabled - using scraping instead
AMAZON_API_CLIENT_ID = ""
AMAZON_API_CLIENT_SECRET = ""
AMAZON_API_REGION = "in"
AMAZON_API_BASE_URL = "https://api.amazon.com"
AMAZON_API_SCOPE = "product:read"
ENABLE_AMAZON_API = False

def parse_int(val, default):
    """Extract digits from string and convert to int, fallback to default."""
    if val is None: return default
    if isinstance(val, int): return val
    try:
        digits = re.sub(r"[^\d]", "", str(val))
        return int(digits) if digits else default
    except Exception:
        return default

# interval (seconds) between scraper cycles.
# Default: 1500 seconds (25 minutes). Override via HF Secret: SCRAPE_INTERVAL or SCRAPE_INTERVAL_MINUTES
SCRAPE_INTERVAL_SECONDS = parse_int(
    get_config("SCRAPE_INTERVAL", os.getenv("SCRAPE_INTERVAL_SECONDS", 1500)),
    1500
)
SCRAPE_INTERVAL_MINUTES = SCRAPE_INTERVAL_SECONDS

# interval (seconds) between individual deal posts from the queue.
# Bot will post deals every 30 minutes (1800 seconds).
POST_INTERVAL_SECONDS = parse_int(
    get_config("POST_INTERVAL", os.getenv("POST_INTERVAL_SECONDS", 1800)),
    1800
)

USE_DIRECT = str(get_config("USE_DIRECT", "0")).strip().lower() in ("1", "true", "yes", "on")

DEALS_PER_RUN = parse_int(get_config("DEALS_PER_RUN", 0), 0)
AMAZON_COUNTRY = get_config("AMAZON_COUNTRY", "in")
MAX_PRICE = float(get_config("MAX_PRICE", 5000))
LOOT_THRESHOLD = float(get_config("LOOT_THRESHOLD", 500))
MIN_DISCOUNT = float(get_config("MIN_DISCOUNT", 30))
LOOT_MIN_DISCOUNT = float(get_config("LOOT_MIN_DISCOUNT", 30))

# Temporary reject cooldown. Products that have no price, are too costly, or
# do not meet the discount filter will be retried after this many seconds
# instead of being added forever to sent history.
REJECTED_DEAL_COOLDOWN_SECONDS = parse_int(get_config("REJECTED_DEAL_COOLDOWN_SECONDS", 86400), 86400)

# Old deployments stored skipped/non-qualifying products in sent_deals too,
# which can block future real deals. Keep this off unless you are certain
# sent_deals contains only products actually posted to Telegram.
STRICT_SENT_HISTORY = str(get_config("STRICT_SENT_HISTORY", "0")).strip().lower() in ("1", "true", "yes", "on")

DATA_PATH = get_config("DATA_PATH", "/data")

# ── GA4 Measurement Protocol ─────────────────────────────────────────────
# Set GA4_MEASUREMENT_ID (e.g. G-XXXXXXXXXX)
# Set GA4_API_SECRET (Measurement Protocol API secret from GA4 console)
# Leave empty to disable GA4 tracking.
GA4_MEASUREMENT_ID = get_config("GA4_MEASUREMENT_ID", "G-3ECY9K5480")
GA4_API_SECRET = get_config("GA4_API_SECRET", "")  # Set this in Render/HF env vars
