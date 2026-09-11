"""
Amazon Deal Telegram Bot - Resilience v34 (Ultimate Bridge)
========================================================
Fix: Exclude BRIDGE_URL from IP-mirroring (Avoid CF-on-CF recursion)
     Bridge-First strategy for HF environments
     Enhanced trace logging for connection lifecycle
     Optimized Cloudflare IP pool
"""

import socket
import threading
import random
import os
import sys
import time
import requests
import urllib3
import re
import logging
import schedule
import ssl
from urllib.parse import quote_plus

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

try:
    from flask import Flask, jsonify, request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

import json
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# ── LOGGING ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, AFFILIATE_TAG, UTM_TAG,
    SCRAPE_INTERVAL_MINUTES, POST_INTERVAL_SECONDS, AMAZON_COUNTRY, MAX_PRICE,
    LOOT_THRESHOLD, MIN_DISCOUNT, LOOT_MIN_DISCOUNT, BRIDGE_URL,
    USE_DIRECT, DATA_PATH, ENABLE_BRIDGE,
    GA4_MEASUREMENT_ID, GA4_API_SECRET, REJECTED_DEAL_COOLDOWN_SECONDS,
    STRICT_SENT_HISTORY
)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── ENVIRONMENT SENSE ──────────────────────────────────────────────────
# Standard HF detection
IS_HF = any(x in os.environ for x in ["HF_SPACE", "SPACE_ID", "SPACE_HOST"])

# Render detection (Render blocks direct Telegram API)
IS_RENDER = any(x in os.environ for x in ["RENDER", "RENDER_SERVICE_ID", "RENDER_INSTANCE_ID"])

# ── GHOST PROTOCOL (v34: Forced on HF) ────────────────────────────────────
CF_IPS = [
    "104.21.75.3", "172.67.209.148", "104.21.75.4", "172.67.209.149",
    "104.16.132.229", "104.16.133.229", "108.162.192.150", "162.159.135.42",
    "172.64.154.148", "104.18.3.161", "104.18.2.161", "172.64.155.249",
    "104.18.32.144", "104.18.33.144"
]
PRIMARY_PORT   = 443
FAILOVER_PORTS = [8443, 2053, 2083, 2087, 2096, 8880]

class GhostProtocolUltra:
    def __init__(self):
        self.active_ip      = random.choice(CF_IPS)
        self.active_port    = PRIMARY_PORT
        self.domains        = ["api.telegram.org"]
        self.is_patched     = False
        self.ua             = UserAgent()
        self.failed_routes  = set() 
        self.rotation_count = 0

    def setup(self):
        target_bridge = os.getenv("BRIDGE_URL", "").strip() or BRIDGE_URL.strip()
        self.bridge_domain = None
        if target_bridge:
            match = re.search(r"https?://([^/:]+)", target_bridge)
            if match:
                domain = match.group(1)
                if domain not in self.domains:
                    self.domains.append(domain)
                self.bridge_domain = domain
        
        # On HF/Render, DNS might resolve but egress to specific IPs might be throttled/poisoned.
        # We ALWAYS force Ghost Protocol on HF/Render.
        if IS_HF or IS_RENDER:
            env_name = "HuggingFace" if IS_HF else "Render"
            logger.warning(f"🦾 Environment: {env_name}. Forcing Ghost Protocol...")
            self.patch_connection()
        else:
            # LOCAL MODE: Skip Ghost Protocol, use direct connections
            logger.info("🏠 Local environment detected. Using direct connections (Ghost Protocol disabled).")
            try:
                socket.gethostbyname("google.com")
                logger.info("📡 DNS resolution looks normal.")
            except Exception:
                logger.warning("👻 DNS Fail Detected. Activating Ghost Protocol...")
                self.patch_connection()

    def patch_connection(self):
        if self.is_patched: return
        from urllib3.util import connection
        _orig   = connection.create_connection
        domains = self.domains

        def patched(address, *args, **kwargs):
            host, port = address
            if host in domains and host != self.bridge_domain:
                return _orig((self.active_ip, self.active_port), *args, **kwargs)
            return _orig(address, *args, **kwargs)

        connection.create_connection = patched
        self.is_patched = True
        logger.info("✅ Ghost Protocol Active | Tunneling: %s", ", ".join(self.domains[:3]))

    def reset(self):
        self.failed_routes.clear()
        self.active_ip   = random.choice(CF_IPS)
        self.active_port = PRIMARY_PORT
        logger.info("♻️ Ghost Protocol Full Reset.")

    def rotate(self, failed_ip=None, failed_port=None):
        if failed_ip and failed_port:
            self.failed_routes.add((failed_ip, failed_port))
        
        candidates = []
        for ip in CF_IPS:
            for p in [PRIMARY_PORT] + FAILOVER_PORTS:
                if (ip, p) not in self.failed_routes:
                    candidates.append((ip, p))
        
        if not candidates:
            self.failed_routes.clear()
            self.active_ip = random.choice(CF_IPS)
            self.active_port = PRIMARY_PORT
        else:
            self.active_ip, self.active_port = random.choice(candidates)
            
        self.rotation_count += 1
        if self.rotation_count % 3 == 0:
            logger.debug("🔄 Engine Shift %d | %s:%d (Blacklisted: %d)",
                        self.rotation_count, self.active_ip, self.active_port, len(self.failed_routes))

ghost = GhostProtocolUltra()

# ── STREAMLIT INITIALIZATION ──────────────────────────────────────────
status_placeholder = None
_worker_initialized = False # Global flag to prevent multiple threads

def _detect_streamlit_runtime():
    if not HAS_STREAMLIT: return False
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:
        try:
            _ = st.session_state.get
            return True
        except Exception: return False

IS_STREAMLIT_RUN = _detect_streamlit_runtime()

if IS_STREAMLIT_RUN:
    st.set_page_config(page_title="Amazon Bot v34", page_icon="🚀", layout="wide")
    st.title("🚀 Amazon Resilient Bot v34")
    bridge_val = os.getenv("BRIDGE_URL", "Not set")
    if IS_HF:
        mode = "🟢 HuggingFace"
    elif IS_RENDER:
        mode = "🟠 Render"
    else:
        mode = "🔵 Local"
    st.markdown(f"**Mode:** {mode} | **Bridge:** `{bridge_val}`")
    status_placeholder = st.empty()
else:
    env_name = "HuggingFace" if IS_HF else "Render" if IS_RENDER else "Local"
    logger.info("🖥️ Headless Mode | Environment: %s", env_name)

# ── REQUEST ENGINE ────────────────────────────────────────────────────────
def get_stealth_headers():
    return {
        "User-Agent":                ghost.ua.random,
        "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language":           "en-US,en;q=0.5",
        "Connection":                "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

def safe_request(method, url, max_retries=6, **kwargs):
    kwargs.setdefault("verify",  False)
    kwargs.setdefault("timeout", 45) # Aggressive timeout for high-latency HF egress
    last_error = ""

    for attempt in range(max_retries):
        try:
            r = requests.request(method, url, **kwargs)
            return r
        except (requests.exceptions.SSLError, urllib3.exceptions.SSLError) as e:
            last_error = f"SSL: {e}"
            ghost.rotate(ghost.active_ip, ghost.active_port)
            time.sleep(1)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = f"Net: {e}"
            ghost.rotate(ghost.active_ip, ghost.active_port)
            time.sleep(2)
        except Exception as e:
            last_error = f"Err: {e}"
            time.sleep(1)

    logger.debug("safe_request failed: %s | %s", url[:60], last_error[:80])
    return None

def parse_money_value(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("Amount", "amount", "AmountValue", "amountValue", "Value", "value", "DisplayAmount", "displayAmount"):
            parsed = parse_money_value(value.get(key))
            if parsed is not None:
                return parsed
        return None
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(value))
    return float(match.group(1).replace(",", "")) if match else None

def format_price_value(value):
    parsed = parse_money_value(value)
    if parsed is None:
        return "?"
    return str(int(parsed)) if parsed.is_integer() else f"{parsed:.2f}".rstrip("0").rstrip(".")

def first_nested_value(data, paths):
    for path in paths:
        cur = data
        for key in path:
            if isinstance(cur, dict):
                cur = cur.get(key)
            elif isinstance(cur, list) and isinstance(key, int) and 0 <= key < len(cur):
                cur = cur[key]
            else:
                cur = None
                break
        if cur is not None:
            return cur
    return None

# ── GA4 MEASUREMENT PROTOCOL ─────────────────────────────────────────────
def track_ga4_event(event_name, params, client_id="telegram_bot"):
    """Fire a GA4 Measurement Protocol event (non-blocking, best-effort)."""
    if not GA4_MEASUREMENT_ID or not GA4_API_SECRET:
        return  # GA4 not configured — skip silently

    def _send():
        try:
            url = (
                f"https://www.google-analytics.com/mp/collect"
                f"?measurement_id={GA4_MEASUREMENT_ID}"
                f"&api_secret={GA4_API_SECRET}"
            )
            payload = {
                "client_id": str(client_id),
                "events": [{"name": event_name, "params": params}]
            }
            r = requests.post(url, json=payload, timeout=10, verify=False)
            if r.status_code == 204:
                logger.info("📊 GA4 tracked: %s | %s", event_name, params.get("link", "")[:60])
            else:
                logger.debug("GA4 non-204: %s", r.status_code)
        except Exception as e:
            logger.debug("GA4 track error: %s", e)

    threading.Thread(target=_send, daemon=True).start()

# ── TELEGRAM HELPER ───────────────────────────────────────────────────────
def tg_request(endpoint, **kwargs):
    bridge = BRIDGE_URL.strip().rstrip("/") if ENABLE_BRIDGE else ""
    
    # Connection priority based on environment or direct override:
    # - USE_DIRECT=true: always use direct Telegram calls
    # - HF/Render: Bridge first (Direct is blocked)
    # - Local: Direct first (more reliable)
    routes = []
    if USE_DIRECT:
        routes = ["direct"]
    else:
        if ENABLE_BRIDGE and bridge:
            routes.append("bridge")
        routes.append("direct")

    if not routes:
        logger.error("❌ No Telegram routes available!")
        return None

    if USE_DIRECT and (IS_HF or IS_RENDER):
        logger.warning("⚠️ USE_DIRECT enabled; forcing direct Telegram traffic even though this environment may block it.")

    if not bridge and (IS_HF or IS_RENDER) and not USE_DIRECT:
        logger.warning("⚠️ BRIDGE_URL is not set. Bot might be blocked on this platform.")

    for route in routes:
        is_bridge = route == "bridge"
        if is_bridge:
            url = f"{bridge}/bot{TELEGRAM_BOT_TOKEN}/{endpoint}"
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{endpoint}"

        logger.info("📡 TG Request via %s...", "Bridge" if is_bridge else "Direct")
        request_kwargs = dict(kwargs)
        request_kwargs.setdefault("timeout", 12 if is_bridge else 8)
        request_kwargs.setdefault("max_retries", 1)
        r = safe_request("POST", url, **request_kwargs)
        if r and r.status_code == 200:
            return r

        status = r.status_code if r else "Timeout/Blocked"
        logger.warning("⚠️ TG via %s failed (%s)", "Bridge" if is_bridge else "Direct", status)

        if (IS_HF or IS_RENDER) and is_bridge:
            ghost.rotate(ghost.active_ip, ghost.active_port)

    return None

# ── EXTRACTION ────────────────────────────────────────────────────────────
def extract_price_from_block(block):
    if not block: return "?"
    try:
        whole = block.select_one(".a-price-whole")
        fraction = block.select_one(".a-price-fraction")
        if whole:
            w = re.sub(r"[^\d]", "", whole.get_text())
            if fraction:
                f = re.sub(r"[^\d]", "", fraction.get_text())
                return f"{w}.{f}" if f else w
            return w
    except Exception: pass
    
    # Fallback to general search if specific classes fail
    m = re.search(r"₹\s*([\d,]+(?:\.\d+)?)", block.get_text())
    if not m:
        m = re.search(r"([\d,]+(?:\.\d+)?)", block.get_text())
    return format_price_value(m.group(1)) if m else "?"

# Amazon API payload parsing removed - using web scraping instead

# Amazon API removed - using web scraping instead
def fetch_amazon_product_data(asin):
    """Deprecated: Amazon API removed. Always returns None."""
    return None


def extract_product_data(soup, asin):
    # Title
    t_node = (soup.select_one("#productTitle") or 
              soup.select_one(".product-title") or 
              soup.select_one("#title") or
              soup.select_one("h1.a-size-large"))
    title = t_node.get_text().strip() if t_node else ""
    if not title:
        meta = (soup.select_one('meta[name="title"]') or 
                soup.select_one('meta[property="og:title"]'))
        if meta: title = meta.get("content", "")
    title = re.sub(r'^(Amazon\.(in|com|co\.uk)[:\s]+)', '', title, flags=re.I).strip()
    title = (title[:80] + "...") if len(title) > 80 else title
    title = title or f"Amazon Item ({asin})"
    
    # Current Price
    price = "?"
    core = soup.select_one("#corePriceDisplay_desktop_feature_div .a-price:not(.a-text-strike)")
    if core: price = extract_price_from_block(core)
    if price == "?":
        apex = soup.select_one("#apex_offerDisplay_desktop .a-price:not(.a-text-strike)")
        if apex: price = extract_price_from_block(apex)
    if price == "?":
        for sel in ["#priceblock_ourprice", "#priceblock_dealprice", "#priceblock_saleprice", ".a-price.priceToPay", ".priceBlockBuyingPriceString"]:
            node = soup.select_one(sel)
            if node:
                m = re.search(r"([\d,]+(?:\.\d+)?)", node.get_text())
                if m: price = m.group(1).replace(",", ""); break
    if price == "?":
        for sel in [
            ".priceToPay .a-offscreen",
            ".apexPriceToPay .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
            "#corePriceDisplay_mobile_feature_div .a-price .a-offscreen",
            "#tp_price_block_total_price_ww .a-offscreen",
            "[data-a-color='price'] .a-offscreen",
            "span.a-price:not(.a-text-strike) .a-offscreen",
        ]:
            node = soup.select_one(sel)
            if node:
                price = format_price_value(node.get_text(" ", strip=True))
                if price != "?":
                    break
    
    # Original Price (MRP)
    orig = "?"
    core_orig = soup.select_one("#corePriceDisplay_desktop_feature_div .a-text-price")
    if core_orig:
        m = re.search(r"([\d,]+(?:\.\d+)?)", core_orig.get_text())
        if m: orig = m.group(1).replace(",", "")
    if orig == "?":
        basis = (soup.select_one(".basisPrice .a-offscreen") or 
                 soup.select_one(".basisPrice span"))
        if basis:
            m = re.search(r"([\d,]+(?:\.\d+)?)", basis.get_text())
            if m: orig = m.group(1).replace(",", "")
    if orig == "?":
        for sel in [
            ".a-price.a-text-price .a-offscreen",
            "[data-a-strike='true'] .a-offscreen",
            ".basisPrice .a-offscreen",
            "#listPrice .a-offscreen",
        ]:
            node = soup.select_one(sel)
            if node:
                orig = format_price_value(node.get_text(" ", strip=True))
                if orig != "?":
                    break
    
    # Sanity: hide orig if <= current price
    try:
        if orig != "?" and price != "?":
            if float(str(orig).replace(",", "")) <= float(str(price).replace(",", "")):
                orig = "?"
    except Exception: pass

    # Discount
    disc = "DEAL"
    disc_val = 0
    d_node = (soup.select_one(".savingsPercentage") or 
              soup.select_one(".reinventPriceSavingsPercentageMargin") or
              soup.select_one("#corePriceDisplay_desktop_feature_div .a-color-price"))
    if d_node:
        m = re.search(r"(\d+)%", d_node.get_text())
        if m:
            disc_val = int(m.group(1))
            disc = f"{disc_val}%"
            
    # CRITICAL FALLBACK: If price is "?" but we have MRP and Discount
    if price == "?" and orig != "?" and disc_val > 0:
        try:
            mrp_val = float(str(orig).replace(",", ""))
            calc_price = mrp_val * (1 - (disc_val / 100))
            price = str(round(calc_price))
            logger.info("💡 Calculated Price: ₹%s (MRP ₹%s - %s%%)", price, orig, disc_val)
        except Exception: pass
    
    rating = "4.2"
    r_node = (soup.select_one("span.a-icon-alt") or 
              soup.select_one("i.a-icon-star span"))
    if r_node:
        m = re.search(r"(\d+\.\d+)", r_node.get_text())
        if m: rating = m.group(1)
        
    # --- Image extraction ---
    image_url = None
    # common selectors for main product image
    img_node = (soup.select_one("#imgTagWrapperId img") or
                soup.select_one("#landingImage") or
                soup.select_one("img[data-old-hires]") or
                soup.select_one(".a-dynamic-image") or
                soup.select_one("img[data-a-dynamic-image]") or
                soup.select_one("#main-image-container img"))
    
    if img_node:
        logger.debug("📸 Found img_node via: %s", img_node.name)
        # 1. Try data-old-hires or hiRes or large (highest priority)
        image_url = img_node.get("data-old-hires") or img_node.get("data-hi-res") or img_node.get("data-large") or img_node.get("src")
        logger.debug("📸 Initial image_url: %s", image_url)
        
        # 2. Check data-a-dynamic-image (contains a map of URL -> [width, height])
        dai = img_node.get("data-a-dynamic-image")
        if dai:
            try:
                j = json.loads(dai)
                if isinstance(j, dict) and j:
                    # pick the URL with the largest dimensions (area)
                    max_area = 0
                    best_url = image_url
                    for url, dims in j.items():
                        if isinstance(dims, list) and len(dims) >= 2:
                            area = dims[0] * dims[1]
                            if area > max_area:
                                max_area = area
                                best_url = url
                    image_url = best_url
            except Exception:
                pass
        
        # 3. Fallback to srcset (select the last/highest resolution)
        if not image_url or "._SS" in image_url or "._SR" in image_url:
            ss = img_node.get("srcset")
            if ss:
                parts = [p.strip().split(" ")[0] for p in ss.split(",") if p.strip()]
                if parts:
                    image_url = parts[-1]

    # normalization & cleaning
    if image_url:
        logger.debug("📸 Before cleaning: %s", image_url)
        # Strip query params
        image_url = image_url.split("?")[0]
        # CRITICAL: Clean Amazon's size-limiting tags (e.g. ._AC_SR38,50_ or ._SL1500_)
        # This converts a thumbnail URL to its high-res original
        # Safer regex: must follow a dot and underscore, and end with an underscore and dot
        image_url = re.sub(r"\._[A-Z0-9,]+_\.", ".", image_url)
        # Fallback for tags like ._SL1500_ (no trailing dot-underscore)
        image_url = re.sub(r"\._[A-Z0-9,]+_", "", image_url)
        logger.info("📸 Final image_url: %s", image_url)
    else:
        logger.warning("📸 No image found for ASIN %s", asin)
    
    logger.info("📊 %s | ₹%s (MRP ₹%s) | %s OFF | %s", asin, price, orig, disc, title[:30])

    return {
        "title": title, "current_price": price, "original_price": orig, 
        "discount": disc, "discount_val": disc_val, "rating": rating,
        "image": image_url
    }

# ── PERSISTENCE ────────────────────────────────────────────────────────────
# Use configured DATA_PATH if provided; otherwise fallback to /data or current folder.
DATA_BASE = DATA_PATH if os.path.exists(DATA_PATH) else ("/data" if os.path.exists("/data") else ".")
SENT_DEALS_FILE = os.path.join(DATA_BASE, "sent_deals.txt")
DEAL_QUEUE_FILE = os.path.join(DATA_BASE, "deal_queue.json")  # Single definition — do NOT redefine below
DEAL_HISTORY_FILE = os.path.join(DATA_BASE, "deal_history.json")
REJECTED_DEALS_FILE = os.path.join(DATA_BASE, "rejected_deals.json")
DEAL_CACHE_FILE = os.path.join(DATA_BASE, "deal_cache.json")
MAX_HISTORY_ENTRIES = 500  # Increased to remember more deals

if DATA_BASE == ".":
    logger.warning("⚠️ Using ephemeral storage. Deals WILL repeat after Render restart.")
    logger.warning("💡 Tip: Attach a Persistent Disk to /data in Render for a permanent fix.")
else:
    logger.info("💾 Persistent storage active at %s", DATA_BASE)

def load_sent_deals():
    sent_list = set()

    # Always load from deal history and local sent-deals file.
    if os.path.exists(DEAL_HISTORY_FILE):
        try:
            with open(DEAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            if isinstance(history, list):
                sent_list.update(
                    str(item.get("asin", "")).strip().upper()
                    for item in history
                    if isinstance(item, dict) and item.get("asin")
                )
        except Exception as e:
            logger.debug("Posted history load failed: %s", e)

    if os.path.exists(SENT_DEALS_FILE):
        try:
            with open(SENT_DEALS_FILE, "r", encoding="utf-8") as f:
                sent_list.update(line.strip().upper() for line in f if line.strip())
        except Exception as e:
            logger.debug("Local sent-deals load failed: %s", e)

    # Optional remote sync from Bridge.
    bridge_base = BRIDGE_URL.strip().rstrip("/") if ENABLE_BRIDGE else ""
    if bridge_base:
        try:
            r = safe_request("GET", f"{bridge_base}/sent_deals", timeout=10)
            if r and r.status_code == 200:
                remote_asins = r.json()
                if isinstance(remote_asins, list):
                    count_before = len(sent_list)
                    sent_list.update(a.upper() for a in remote_asins)
                    logger.info("💾 Remote history synced (+%d remote, %d total)",
                                len(sent_list) - count_before, len(sent_list))
        except Exception as e:
            logger.debug("Remote Load Fail: %s", e)

    if not STRICT_SENT_HISTORY:
        return sent_list

    # 0. Merge legacy sent_deals.json (one-time migration) into sent_deals.txt
    legacy_json = os.path.join(".", "sent_deals.json")
    if os.path.exists(legacy_json):
        try:
            with open(legacy_json, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            if isinstance(legacy, list) and legacy:
                existing_txt = set()
                if os.path.exists(SENT_DEALS_FILE):
                    with open(SENT_DEALS_FILE, "r", encoding="utf-8") as ef:
                        existing_txt = set(line.strip().upper() for line in ef if line.strip())
                new_entries = [a.upper() for a in legacy if a.upper() not in existing_txt]
                if new_entries:
                    with open(SENT_DEALS_FILE, "a", encoding="utf-8") as f:
                        f.write("\n".join(new_entries) + "\n")
                    logger.info("✅ Migrated %d ASINs from sent_deals.json → sent_deals.txt", len(new_entries))
                os.rename(legacy_json, legacy_json + ".migrated")
        except Exception as e:
            logger.warning("Legacy migration failed: %s", e)

    return sent_list

def save_sent_deal(asin):
    asin = asin.upper()
    # 1. Save to local file
    try:
        with open(SENT_DEALS_FILE, "a", encoding="utf-8") as f:
            f.write(asin + "\n")
            f.flush() # Ensure it's written to disk
            os.fsync(f.fileno()) # Force write to disk
    except Exception as e:
        logger.error("❌ Local Save Fail (%s): %s", asin, e)

    # 2. Sync to Bridge (Cloudflare KV)
    bridge_base = BRIDGE_URL.strip().rstrip("/") if ENABLE_BRIDGE else ""
    if bridge_base:
        try:
            # Send to bridge in background-ish (short timeout)
            safe_request("POST", f"{bridge_base}/sent_deals", json={"asin": asin}, timeout=5)
        except Exception: pass

def load_rejected_deals():
    now = time.time()
    rejected = {}
    if os.path.exists(REJECTED_DEALS_FILE):
        try:
            with open(REJECTED_DEALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for asin, ts in data.items():
                    asin = str(asin).strip().upper()
                    try:
                        ts = float(ts)
                    except (TypeError, ValueError):
                        continue
                    if asin and now - ts < REJECTED_DEAL_COOLDOWN_SECONDS:
                        rejected[asin] = ts
        except Exception as e:
            logger.debug("Rejected deals load failed: %s", e)
    return rejected

def save_rejected_deal(asin):
    asin = str(asin).strip().upper()
    if not asin:
        return
    try:
        rejected = load_rejected_deals()
        rejected[asin] = time.time()
        with open(REJECTED_DEALS_FILE, "w", encoding="utf-8") as f:
            json.dump(rejected, f, indent=4)
    except Exception as e:
        logger.error("Error saving rejected deal %s: %s", asin, e)

def load_deal_history():
    if os.path.exists(DEAL_HISTORY_FILE):
        try:
            with open(DEAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return []

def save_deal_to_history(data, asin):
    try:
        history = load_deal_history()
        
        # India Standard Time (IST) = UTC + 5:30
        ist = timezone(timedelta(hours=5, minutes=30))
        scraped_at = datetime.now(ist).isoformat()
        
        domain = "amazon.in" if AMAZON_COUNTRY == "in" else "amazon.com"
        affiliate_link = f"https://www.{domain}/dp/{asin}?tag={AFFILIATE_TAG}&utm_source={UTM_TAG}"
        
        entry = {
            "asin": asin,
            "product_name": data.get("title", ""),
            "original_price": data.get("original_price", "?"),
            "deal_price": data.get("current_price", "?"),
            "discount_percentage": data.get("discount_val", 0),
            "affiliate_link": affiliate_link,
            "image": data.get("image", ""),
            "rating": data.get("rating", "4.2"),
            "scraped_at": scraped_at
        }
        
        # Avoid duplicates in recent history
        history = [e for e in history if e["asin"] != asin]
        history.insert(0, entry)
        
        # Limit history size
        if len(history) > MAX_HISTORY_ENTRIES:
            history = history[:MAX_HISTORY_ENTRIES]
            
        with open(DEAL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
    except Exception as e:
        logger.error("Error saving deal to history: %s", e)

# ── QUEUE MANAGEMENT ──────────────────────────────────────────────────────
# NOTE: DEAL_QUEUE_FILE is defined above (near SENT_DEALS_FILE) — do not redefine here.

def load_queue():
    if os.path.exists(DEAL_QUEUE_FILE):
        try:
            with open(DEAL_QUEUE_FILE, "r") as f:
                data = json.load(f)
                # Handle legacy format (list instead of dict)
                if isinstance(data, list):
                    data = {"asin_list": data, "last_post_time": 0}

                # Ensure all required fields exist
                if "asin_list" not in data: data["asin_list"] = []
                if "last_post_time" not in data: data["last_post_time"] = 0
                if "last_scrape_time" not in data: data["last_scrape_time"] = 0  # NEW: separate scrape tracker
                if "attempts" not in data: data["attempts"] = {}
                return data
        except Exception as e:
            logger.error("Error loading queue: %s", e)
    return {"asin_list": [], "last_post_time": 0, "last_scrape_time": 0, "attempts": {}}

def save_queue(data):
    try:
        with open(DEAL_QUEUE_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error("Error saving queue: %s", e)

def load_deal_cache():
    if os.path.exists(DEAL_CACHE_FILE):
        try:
            with open(DEAL_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug("Error loading deal cache: %s", e)
    return {}

def save_deal_cache(data):
    try:
        now = time.time()
        fresh = {
            asin: deal for asin, deal in data.items()
            if isinstance(deal, dict) and now - float(deal.get("cached_at", now)) < 43200
        }
        with open(DEAL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(fresh, f, indent=2)
    except Exception as e:
        logger.debug("Error saving deal cache: %s", e)

def extract_listing_card_data(html):
    soup = BeautifulSoup(html, "lxml")
    deals = {}
    links = soup.select("a[href*='/dp/'], a[href*='/gp/product/']")

    for link in links:
        href = link.get("href", "")
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", href)
        if not match:
            continue

        asin = match.group(1).upper()
        card = (
            link.find_parent(attrs={"id": "gridItemRoot"}) or
            link.find_parent(attrs={"data-asin": True}) or
            link.find_parent("div")
        )
        for _ in range(4):
            if not card:
                break
            if card.select_one(".a-price, .a-offscreen"):
                break
            card = card.find_parent("div")
        if not card:
            continue

        price_node = card.select_one(".a-price:not(.a-text-strike) .a-offscreen") or card.select_one(".a-price .a-offscreen")
        price = format_price_value(price_node.get_text(" ", strip=True) if price_node else None)
        if price == "?":
            continue

        orig_node = (
            card.select_one(".a-price.a-text-price .a-offscreen") or
            card.select_one("[data-a-strike='true'] .a-offscreen")
        )
        orig = format_price_value(orig_node.get_text(" ", strip=True) if orig_node else None)

        card_text = card.get_text(" ", strip=True)
        disc_match = re.search(r"(\d+)\s*%", card_text)
        disc_val = int(disc_match.group(1)) if disc_match else 0
        if disc_val == 0 and orig != "?":
            try:
                cur = float(price)
                mrp = float(orig)
                if mrp > cur:
                    disc_val = int(round(((mrp - cur) / mrp) * 100))
            except Exception:
                disc_val = 0

        img = card.select_one("img")
        title = (img.get("alt") or "").strip() if img else ""
        if not title:
            title = re.sub(r"\s+", " ", card_text).strip()[:80]
        title = title or f"Amazon Item ({asin})"

        image_url = ""
        if img:
            image_url = img.get("data-old-hires") or img.get("src") or ""

        deals[asin] = {
            "title": title[:80],
            "current_price": price,
            "original_price": orig,
            "discount": f"{disc_val}%" if disc_val else "DEAL",
            "discount_val": disc_val,
            "rating": "4.2",
            "image": image_url,
            "cached_at": time.time(),
        }

    return deals

# ── PROMO DEALS ───────────────────────────────────────────────────────────
cached_promo_asins = set()

def get_promo_asins(limit=5):
    import csv
    global cached_promo_asins
    promo_file = "amazon_promo_deals.csv"
    if not os.path.exists(promo_file):
        return []
    try:
        with open(promo_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            asins = []
            for row in reader:
                if row and len(row) > 0:
                    asin = row[0].strip().upper()
                    asins.append(asin)
            
            # Cache all ASINs for quick lookup
            if asins:
                cached_promo_asins = set(asins)
                import random
                sample = list(cached_promo_asins)
                random.shuffle(sample)
                return sample[:limit]
            return []
    except Exception as e:
        logger.error("Error reading promo deals: %s", e)
        return []

def is_promo_asin(asin):
    global cached_promo_asins
    asin_clean = asin.strip().upper()
    if not cached_promo_asins:
        # One-time lazy load if set is empty
        _ = get_promo_asins(limit=0)
    return asin_clean in cached_promo_asins

# ── ANALYSIS HELPERS ──────────────────────────────────────────────────────
def get_rating_analysis(rating_str):
    try:
        rating = float(rating_str)
        if rating >= 4.0:
            return "bahut acchi rating hai, log khush hain"
        elif rating >= 3.5:
            return "solid hai, perfect nahi"
        else:
            return "caution - reviews mixed hain"
    except Exception:
        return "Reviews dekhne mein koi major red flag nahi mila"

def get_product_category(title):
    t = title.lower()
    electronics = ["earbuds", "phone", "laptop", "watch", "camera", "led", "tv", "speaker", "mouse", "keyboard", "cable", "adapter", "power bank", "tablet", "headphone"]
    home = ["kitchen", "cook", "bed", "towel", "bottle", "rack", "mop", "detergent", "cleaner", "home", "decor", "furniture", "pillow", "curtain"]
    
    if any(x in t for x in electronics): return "electronics"
    if any(x in t for x in home): return "home"
    return "general"

def extract_key_feature(title):
    # Try to extract a specific feature from brackets or common patterns
    m = re.search(r"\(([^)]+)\)", title)
    if m: return m.group(1).split(",")[0].strip()
    
    # Otherwise, pick a meaningful word from the title (e.g., after the second word)
    parts = title.split()
    if len(parts) > 3:
        # Try to find words like 'with', 'and', or just return a snippet
        for i, word in enumerate(parts):
            if word.lower() in ["with", "featuring", "for"]:
                return " ".join(parts[i:])[:30]
        return " ".join(parts[1:4])
    return title[:30]

def get_use_cases(title, category):
    t = title.lower()
    if category == "electronics":
        if any(x in t for x in ["gaming", "rgb", "mechanical"]):
            return "Gaming / High performance", "Professional studio use"
        return "Daily Office / Study use", "Heavy duty industrial projects"
    elif category == "home":
        if any(x in t for x in ["luxury", "premium", "gift"]):
            return "Gifting / Premium home setup", "Rough outdoor use"
        return "Daily home needs / Practical use", "Decorative only / Showpiece"
    
    return "Daily personal use / Regular needs", "Professional or commercial use"

BLACKLIST_KEYWORDS = [
    # Food & Snacks
    "snack", "chips", "potato chips", "biscuit", "cookie", "chocolate", "namkeen",
    "kurkure", "lays", "doritos", "pringles", "munch", "kitkat",
    # Baby & Kids
    "toy", "baby", "plush", "doll", "infant", "newborn", "maternity", "diaper",
    "stroller", "pampers", "mamyppo", "huggies", "kids", "tricycle", "junior",
    "ride-on", "scooter", "walker",
    # Jewellery & Accessories
    "jewellery", "jewelry", "necklace", "earring", "bracelet", "bangle", "ring",
    "pendant", "anklet", "maang tikka", "mangalsutra", "jhumka", "jhumki",
    "choker", "gold plated", "silver plated", "oxidised", "antique gold",
    "matte gold", "kundan", "polki", "meenakari", "temple jewellery",
    "fashion jewellery", "imitation jewellery", "artificial jewellery",
    "pearl necklace", "stone necklace", "beaded necklace", "chain necklace",
    "lakshmi", "goddess", "peacock necklace", "traditional necklace",
    "bridal jewellery", "wedding jewellery", "ethnic jewellery",
    # Handbags & Accessories  
    "handbag", "purse", "clutch", "wallet", "tote bag", "sling bag",
    "crossbody", "backpack purse", "ladies bag",
    # Watches (fashion/imitation)
    "analog watch", "quartz watch", "fashion watch",
    # Cosmetics & Beauty
    "lipstick", "foundation", "mascara", "eyeliner", "kajal", "eyeshadow",
    "blush", "concealer", "primer", "highlighter", "bronzer", "serum",
    "face wash", "moisturizer", "sunscreen", "perfume", "deodorant",
    "nail polish", "makeup", "skincare", "hair oil", "shampoo", "conditioner",
    # Clothing & Footwear
    "saree", "sari", "salwar", "kurti", "lehenga", "dupatta", "suit",
    "churidar", "palazzo", "anarkali", "ghagra", "blouse",
    "heels", "sandals", "flip flops", "ethnic wear", "party wear",
]

def is_blacklisted_title(title):
    t_lower = (title or "").lower()
    return any(word in t_lower for word in BLACKLIST_KEYWORDS)

# ── LOGIC ─────────────────────────────────────────────────────────────────
def send_product_message(data, asin):
    try:
        domain = "amazon.in" if AMAZON_COUNTRY == "in" else "amazon.com"
        p_url = f"https://www.{domain}/dp/{asin}?tag={AFFILIATE_TAG}&utm_source={UTM_TAG}"
        
        cur = f"{data['current_price']}" if data['current_price'] != "?" else "Check Price"
        orig = data['original_price'] if data['original_price'] != "?" else ""
        disc = data['discount'] if data['discount'] != "DEAL" else "DEAL"

        # Analysis logic
        rating_val = data.get('rating', '4.2')
        rating_analysis = get_rating_analysis(rating_val)
        category = get_product_category(data['title'])
        key_feature = extract_key_feature(data['title'])
        kharido, mat_kharido = get_use_cases(data['title'], category)

        msg_text = (
            f"🚨 <b>HONEST DEAL ALERT</b> 🚨\n\n"
            f"<b>Product:</b> {data['title']}\n"
            f"<b>Price:</b> ₹{cur} (MRP ₹{orig} - {disc} OFF)\n\n"
            f"🔍 <b>Mera analysis (2 min me padho):</b>\n"
            f"• Rating {rating_val}/5 hai - {rating_analysis}\n"
            f"• {key_feature}\n"
            f"• <b>Main problem kya hai?</b> Reviews dekhne mein koi major red flag nahi mila\n\n"
            f"🎯 <b>Kharido agar:</b> {kharido}\n"
            f"❌ <b>Mat kharido agar:</b> {mat_kharido}\n\n"
            f"📦 <b>Link:</b> <a href='{p_url}'>Buy Now on Amazon</a>\n\n"
            f"Mera channel sirf tested aur filtered deals. Join karne ke liye dhanyavaad 🙏"
        )

        # try to send photo if URL available, otherwise fallback to text
        # --- Snack / Blacklist Filter ---
        if is_blacklisted_title(data.get("title", "")):
            logger.info("🚫 Skipping Blacklisted/Snack: %s", data['title'])
            return False
        if data.get("image"):
            logger.info("📸 Image URL: %s", data.get("image"))
            # Telegram may auto‑blur what it thinks is sensitive.  to avoid that
            # we can optionally send the file as a document instead of a photo.
            use_document = os.getenv("SEND_IMAGE_AS_DOCUMENT", "0") == "1"
            if use_document:
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "document": data["image"],
                    "caption": msg_text,
                    "parse_mode": "HTML",
                }
                r = tg_request("sendDocument", json=payload)
            else:
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "photo": data["image"],
                    "caption": msg_text,
                    "parse_mode": "HTML",
                }
                r = tg_request("sendPhoto", json=payload)
        else:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID, "text": msg_text, "parse_mode": "HTML", "disable_web_page_preview": False
            }
            r = tg_request("sendMessage", json=payload)

        if r and r.status_code == 200:
            logger.info("✅ Posted: %s (₹%s)", asin, data['current_price'])
            # ── GA4: track affiliate_click event ──────────────────────────
            domain = "amazon.in" if AMAZON_COUNTRY == "in" else "amazon.com"
            affiliate_link = f"https://www.{domain}/dp/{asin}?tag={AFFILIATE_TAG}&utm_source={UTM_TAG}"
            track_ga4_event(
                event_name="affiliate_click",
                params={
                    "source":    "telegram",
                    "campaign":  f"deal_{datetime.now(timezone.utc).strftime('%b%Y').lower()}",
                    "link":      affiliate_link,
                    "asin":      asin,
                    "price":     str(data.get('current_price', '?')),
                    "discount":  str(data.get('discount', 'DEAL')),
                },
                client_id=f"bot_{TELEGRAM_CHAT_ID}"
            )
            return True
        return False
            
    except Exception as e:
        logger.error("Post Error (%s): %s", asin, e)
        return False

def cycle_deals():
    try:
        logger.info("🔍 Scraper Cycle Start...")
        domain = "amazon.in" if AMAZON_COUNTRY == "in" else "amazon.com"
        bridge_base = BRIDGE_URL.strip().rstrip("/") if ENABLE_BRIDGE else ""
        
        # expanded bestseller categories per user request; each URL is
        # the `gp/bestsellers/<category>` page on Amazon.  only the ASINs
        # scraped from these pages will be considered (i.e. best sellers
        # only).
        cats = [
            "electronics",
            "kitchen",
            "home",
            "computers",
            "amazon-explore",
            "digital-music",
            "physical-music",
            "digital-videos",
            "physical-books",
            "automotive",
            # Amazon devices subcategories
            "fire-tablet",
            "kindle",
            "echo",
            "fire-tv",
            "furniture",
            "home-improvement",
            "lawn-and-garden",
            "pets",
            "headphones",
            "musical-instruments",
            "business-industrial-supplies",
            "outdoors",
            "tools",
            "sports",
            "pc-components",
            "televisions",
            "health-personal-care"
            # REMOVED: beauty, luxury-beauty, luxury-stores-beauty (cosmetics)
            # REMOVED: jewelry, handbags-and-accessories, shoes, luggage (fashion accessories)
            # REMOVED: apparel, luxury-stores-fashion, handmade (clothing/fashion)
            # REMOVED: watches (imitation watches)
            # REMOVED: ring (Amazon Ring device — can overlap with jewelry searches)
            # REMOVED: amazon-coins
        ]
        random.shuffle(cats)
        targets = [f"https://www.{domain}/gp/bestsellers/{c}" for c in cats]
        
        asins = []
        deal_cache = load_deal_cache()
        # Strategies
        stealth = lambda u: safe_request(
            "GET", u,
            headers=get_stealth_headers(),
            timeout=15,
            max_retries=2
        )
        tunnel = lambda u: (
            safe_request(
                "GET",
                f"{bridge_base}/?url={quote_plus(u)}",
                headers=get_stealth_headers(),
                timeout=15,
                max_retries=2
            ) if bridge_base else None
        )

        strategies = [("Tunnel", tunnel), ("Stealth", stealth)] if IS_HF else [("Stealth", stealth), ("Tunnel", tunnel)]
        
        for name, caller in strategies:
            logger.info("🔎 Trying scraper strategy: %s", name)
            # Check all categories for deals
            for url in targets:
                try:
                    r = caller(url)
                    if r and r.status_code == 200:
                        listing_deals = extract_listing_card_data(r.text)
                        if listing_deals:
                            deal_cache.update(listing_deals)
                            logger.info("ðŸ’¾ Cached %d listing-card deals via [%s]", len(listing_deals), name)
                        found = re.findall(r"/(?:dp|gp/product|gp/slredirect/.*%2Fdp%2F)/([A-Z0-9]{10})", r.text)
                        if found:
                            unique_found = [f for f in set(found) if f not in asins]
                            asins += unique_found
                            logger.info("✅ Found %d new ASINs via [%s] in category %s", len(unique_found), name, url.split("/")[-1])
                    else:
                         logger.debug("[%s] Status %s for %s", name, r.status_code if r else "None", url[:40])
                except Exception:
                    logger.debug("[%s] Request exception for %s", name, url[:60])
                    continue
            if asins: break # If we found enough ASINs via one strategy, stop there to avoid extra traffic

        save_deal_cache(deal_cache)
        
        if not asins:
             promo_asins = get_promo_asins(limit=10)
             if promo_asins:
                 asins += promo_asins
                 logger.info("✅ Fallback: Added %d promo ASINs to the pool", len(promo_asins))
            
        if not asins:
            logger.warning("⚠️ Scraper Output Empty. Waiting next cycle.")
            return 0

        # Dedupe scraped ASINs, then filter posted, cooldown, and queued items.
        candidate_asins = list(dict.fromkeys(a.upper() for a in asins if a))
        sent_deals = load_sent_deals()
        rejected_deals = set(load_rejected_deals().keys())
        asin_list = [a for a in candidate_asins if a not in sent_deals and a not in rejected_deals]
        
        # Also filter out what's already in the queue
        queue_data = load_queue()
        queued_asins = set(a.upper() for a in queue_data.get("asin_list", []))
        asin_list = [a for a in asin_list if a.upper() not in queued_asins]

        random.shuffle(asin_list)
        
        if not asin_list:
            posted_count = sum(1 for a in candidate_asins if a in sent_deals)
            cooldown_count = sum(1 for a in candidate_asins if a not in sent_deals and a in rejected_deals)
            queued_count = sum(1 for a in candidate_asins if a not in sent_deals and a not in rejected_deals and a in queued_asins)
            logger.info(
                "No new deals found. Scraped %d unique ASINs (%d posted before, %d in reject cooldown, %d already queued).",
                len(candidate_asins), posted_count, cooldown_count, queued_count
            )
            return 0

        logger.info("🎯 Found %d candidate deals. Adding to queue.", len(asin_list))
        
        # Add new ASINs to queue
        queue_data["asin_list"].extend(asin_list)
        save_queue(queue_data)
        
        return len(asin_list)

    except Exception as e:
        logger.error("Cycle Fatal: %s", e)
        return 0

def process_one_deal():
    """Extracts and posts one deal from the queue if interval allows."""
    queue_data = load_queue()
    asin_list = queue_data.get("asin_list", [])
    last_post_time = queue_data.get("last_post_time", 0)
    attempts = queue_data.get("attempts", {})

    if not asin_list:
        logger.info("📭 Queue is empty. Waiting for scraper to find new deals...")
        return False

    elapsed = time.time() - last_post_time
    wait_sec = POST_INTERVAL_SECONDS

    if elapsed < wait_sec:
        remaining = int(wait_sec - elapsed)
        if remaining % 300 == 0 or remaining < 60:  # Log every 5 mins or if < 1 min
            logger.info("⏳ Waiting for post interval... (%d seconds remaining, next post in %d min)", remaining, remaining//60)
        return False

    logger.info("📤 POST INTERVAL MET! Ready to post a deal. Queue has %d items.", len(asin_list))

    domain = "amazon.in" if AMAZON_COUNTRY == "in" else "amazon.com"
    bridge_base = BRIDGE_URL.strip().rstrip("/") if ENABLE_BRIDGE else ""

    # Load sent deals ONCE at the start and maintain in-memory set
    # to prevent repeats even within a single processing run
    sent_deals = load_sent_deals()
    deal_cache = load_deal_cache()

    # Try one by one until one works or queue empty
    while asin_list:
        asin = asin_list.pop(0)
        asin_key = asin.upper()
        attempt_count = attempts.get(asin_key, 0)

        # Double check if already sent (in-memory check — updated after each save)
        if asin_key in sent_deals:
            logger.info("⏭️ Skip %s (Already sent — in memory or file)", asin)
            queue_data["asin_list"] = asin_list
            queue_data["attempts"] = attempts
            save_queue(queue_data)
            continue

        logger.info("📦 Processing from queue: %s", asin)

        temp_data = None
        cached_data = deal_cache.get(asin_key)
        if cached_data and cached_data.get("current_price") != "?":
            temp_data = dict(cached_data)
            logger.info("ðŸ’¾ Using cached listing-card price for %s", asin)

        # Skip API - use scraping instead
        if not temp_data:
            p_url = f"https://www.{domain}/dp/{asin}"
            r = None
            fetched = False

            resp = None if (IS_HF or IS_RENDER) else safe_request("GET", p_url, headers=get_stealth_headers(), timeout=10, max_retries=1)
            if resp and resp.status_code == 200 and "captcha" not in resp.text.lower():
                r = resp
                fetched = True
            elif resp is not None:
                logger.debug("⛔ Direct fetch failed for %s | status=%s", asin, resp.status_code)

            if not fetched and bridge_base:
                resp = safe_request("GET", f"{bridge_base}/?url={quote_plus(p_url)}", headers=get_stealth_headers(), timeout=10, max_retries=1)
                if resp and resp.status_code == 200 and "captcha" not in resp.text.lower():
                    r = resp
                    fetched = True
                elif resp is not None:
                    logger.debug("⛔ Bridge fetch failed for %s | status=%s", asin, resp.status_code)

            if fetched and r:
                try:
                    soup = BeautifulSoup(r.text, "lxml")
                    temp_data = extract_product_data(soup, asin)
                except Exception as e:
                    logger.debug("HTML product parsing error for %s: %s", asin, e)

        pv = temp_data.get("current_price", "?") if temp_data else "?"
        title = temp_data.get("title", "") if temp_data else ""

        if is_blacklisted_title(title):
            logger.info("⏭️ Skip %s (Blacklisted keyword match). Marking as handled.", asin)
            save_rejected_deal(asin)
            sent_deals.add(asin_key)
            attempts.pop(asin_key, None)
            queue_data["asin_list"] = asin_list
            queue_data["attempts"] = attempts
            save_queue(queue_data)
            continue

        if pv == "?":
            attempt_count += 1
            has_detail_page = bool(temp_data and title and not title.startswith(f"Amazon Item ({asin})"))
            if (IS_HF or IS_RENDER) and not has_detail_page:
                logger.warning("No product details for %s in hosted mode. Cooling down instead of requeueing.", asin)
                save_rejected_deal(asin)
                attempts.pop(asin_key, None)
            elif attempt_count < 2:
                logger.warning("⚠️ No price for %s. Requeueing for another try (%d/2).", asin, attempt_count)
                attempts[asin_key] = attempt_count
                asin_list.append(asin)
            else:
                logger.warning("⚠️ No price for %s after %d tries. Cooling down.", asin, attempt_count)
                save_rejected_deal(asin)
                attempts.pop(asin_key, None)
            queue_data["asin_list"] = asin_list
            queue_data["attempts"] = attempts
            save_queue(queue_data)
            continue

        try:
            price_val = float(str(pv).replace(",", ""))
            from config import MIN_DISCOUNT
            disc_val = temp_data.get("discount_val", 0)

            if price_val <= MAX_PRICE and disc_val >= MIN_DISCOUNT:
                logger.info("✅ Deal qualifies! Price: ₹%s (max: ₹%s), Discount: %s%% (min: %s%% OFF)", 
                           price_val, MAX_PRICE, disc_val, MIN_DISCOUNT)
                if send_product_message(temp_data, asin):
                    logger.info("🎉 DEAL POSTED SUCCESSFULLY to Telegram: %s", asin)
                    save_sent_deal(asin)
                    sent_deals.add(asin_key)
                    attempts.pop(asin_key, None)
                    save_deal_to_history(temp_data, asin)
                    queue_data["last_post_time"] = time.time()
                    queue_data["asin_list"] = asin_list
                    queue_data["attempts"] = attempts
                    save_queue(queue_data)
                    logger.info("✅ Successfully posted %s (₹%s, %s%% OFF).", asin, pv, disc_val)
                    return True
                else:
                    attempt_count += 1
                    if attempt_count < 3:
                        logger.warning("❌ send_product_message failed for %s. Requeueing (%d/3).", asin, attempt_count)
                        attempts[asin_key] = attempt_count
                        asin_list.append(asin)
                    else:
                        logger.error("❌ send_product_message failed for %s after %d tries. Cooling down.", asin, attempt_count)
                        save_rejected_deal(asin)
                        attempts.pop(asin_key, None)
            else:
                reason = f"₹{pv} > ₹{MAX_PRICE}" if price_val > MAX_PRICE else f"{disc_val}% < {MIN_DISCOUNT}% OFF"
                logger.info("⏭️ Skip %s (%s). Cooling down before retry.", asin, reason)
                save_rejected_deal(asin)
                attempts.pop(asin_key, None)
        except Exception as e:
            logger.error("Processing Logic Error: %s", e)
            attempt_count += 1
            if attempt_count < 3:
                logger.warning("⚠️ Processing error for %s. Requeueing (%d/3).", asin, attempt_count)
                attempts[asin_key] = attempt_count
                asin_list.append(asin)
            else:
                logger.error("⚠️ Processing error for %s after %d tries. Cooling down.", asin, attempt_count)
                save_rejected_deal(asin)
                attempts.pop(asin_key, None)

        queue_data["asin_list"] = asin_list
        queue_data["attempts"] = attempts
        save_queue(queue_data)
        time.sleep(2)

        queue_data["asin_list"] = asin_list
        queue_data["attempts"] = attempts
        save_queue(queue_data)
        time.sleep(2)

    queue_data["attempts"] = attempts
    save_queue(queue_data)
    return False

# ── WORKER ────────────────────────────────────────────────────────────────
def verify_connection():
    logger.info("🛠️ Verifying Connection...")
    for attempt in range(5):
        r = tg_request("getMe")
        if r and r.status_code == 200:
            username = r.json().get("result", {}).get("username", "unknown")
            logger.info("✅ Connection OK → @%s", username)
            return True
        logger.warning("⚠️ Attempt %d failed. Rotating and retrying...", attempt + 1)
        ghost.rotate(ghost.active_ip, ghost.active_port)
        time.sleep(3)
    
    logger.error("❌ Critical: Telegram connection persistent failure.")
    ghost.reset()
    return False

def start_bot_worker():
    # 1. Initialize Ghost Protocol in the background thread (Non-blocking startup)
    ghost.setup()
    
    time.sleep(10)
    env_name = "HuggingFace" if IS_HF else "Render" if IS_RENDER else "Local"
    logger.info("🚀 Resilience v34 Ultra Boots | Environment: %s", env_name)
    logger.info("⚙️ Configuration: Scrape every %d sec | Post every %d sec (%d min)", 
                SCRAPE_INTERVAL_MINUTES, POST_INTERVAL_SECONDS, POST_INTERVAL_SECONDS//60)
    logger.info("💰 Filters: Max Price ₹%d | Min Discount %d%%", MAX_PRICE, MIN_DISCOUNT)
    verify_connection()
    
    scrape_counter = 0
    while True:
        try:
            # 1. Try to process a deal from queue
            posted = process_one_deal()

            # 2. Scrape logic: Only scrape if queue is empty OR scrape interval has passed
            #    Use last_scrape_time (not last_post_time) to avoid scraping too frequently
            queue_data = load_queue()
            last_scrape_time = queue_data.get("last_scrape_time", 0)
            elapsed_since_last_scrape = (
                time.time() - last_scrape_time
                if last_scrape_time > 0
                else SCRAPE_INTERVAL_MINUTES + 1  # SCRAPE_INTERVAL_MINUTES is now in seconds
            )
            scrape_interval_sec = SCRAPE_INTERVAL_MINUTES  # Already in seconds

            queue_empty = not queue_data.get("asin_list")
            interval_met = elapsed_since_last_scrape >= scrape_interval_sec

            if queue_empty and not interval_met:
                logger.info("🔍 Queue is empty. Triggering immediate scrape on restart/reset.")
                interval_met = True

            if interval_met:
                if queue_empty:
                    logger.info("🔍 Queue empty. Starting cycle...")
                else:
                    logger.info("🕒 Scrape interval met (%d sec). Starting cycle...", SCRAPE_INTERVAL_MINUTES)
                count = cycle_deals()
                queue_data = load_queue()  # reload after cycle_deals modifies it
                queue_data["last_scrape_time"] = time.time()
                save_queue(queue_data)
                logger.info("🕒 Next scrape in %d seconds.", SCRAPE_INTERVAL_MINUTES)
            elif not queue_empty:
                remaining = int(scrape_interval_sec - elapsed_since_last_scrape)
                if remaining < 60 or remaining % 300 <= 5:
                    logger.info("📭 Queue pending. Next scrape in %d seconds.", max(remaining, 0))

            # 3. Frequent polling sleep (5 seconds for responsive behavior)
            time.sleep(5)

        except Exception as e:
            logger.error("Worker Error: %s. Restarting in 30s...", e)
            time.sleep(30)

# ── HEALTH CHECK SERVER ──────────────────────────────────────────────────
app = None
if HAS_FLASK:
    app = Flask(__name__)
    @app.route('/')
    def health():
        return {"status": "ok", "bot": "active", "version": "v34"}, 200

    @app.route('/api/deals')
    def get_deals():
        """Return latest deals from history"""
        limit = int(request.args.get('limit', 20))
        deals = load_deal_history()
        return jsonify(deals[:limit])

    @app.route('/api/deals/search')
    def search_deals():
        """Search deals by product name in history"""
        query = request.args.get('query', '').lower()
        limit = int(request.args.get('limit', 5))
        
        all_deals = load_deal_history()
        if not query:
            return jsonify(all_deals[:limit])
            
        results = [d for d in all_deals if query in d.get('product_name', '').lower()]
        return jsonify(results[:limit])

def run_health_check():
    if not app:
        logger.warning("⚠️ Flask not initialized. Skipping health check server.")
        return
    
    # Render: 10000 | HF: 7860 | Default: 10000
    port = int(os.environ.get("PORT", 10000))
    logger.info("🌐 Starting Health Check Server on port %d", port)
    try:
        # Explicit binding to 0.0.0.0 is critical for Render
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error("❌ Health Check Server failed: %s", e)

# ── STREAMLIT MAIN ──────────────────────────────────────────────────────────────────
if HAS_STREAMLIT:
    st_cache_resource = st.cache_resource
else:
    def st_cache_resource(func):
        return func


def initialize_runtime():
    global _worker_initialized
    if _worker_initialized:
        return True

    _worker_initialized = True
    logger.info("🧵 Starting bot worker thread for production/runtime startup...")
    t = threading.Thread(target=start_bot_worker, daemon=True)
    t.start()
    return True

@st_cache_resource
def start_singleton_worker():
    return initialize_runtime()

if IS_STREAMLIT_RUN:
    start_singleton_worker()
else:
    initialize_runtime()
    
    if status_placeholder:
        status_placeholder.success("✅ Resilience v34 Active.")
    st.divider()
    st.subheader("📋 Activity Monitor")
    if os.path.exists("bot.log"):
        with open("bot.log", "r", encoding="utf-8") as f:
            st.code("".join(f.readlines()[-60:]))

# ── HEADLESS / TERMINAL MODE ──────────────────────────────────────────────
if __name__ == "__main__" and not IS_STREAMLIT_RUN:
    logger.info("🖥️ Headless Mode Start. Version: v34")
    initialize_runtime()

    if os.getenv("RUN_DEV_SERVER", "0").strip().lower() in ("1", "true", "yes", "on") and HAS_FLASK:
        run_health_check()
    else:
        logger.info("🛣️ Production server is expected to run via Gunicorn/Uvicorn; keeping the process alive.")
        while True:
            time.sleep(60)
