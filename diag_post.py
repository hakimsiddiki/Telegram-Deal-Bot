"""
Diagnostic script to test Telegram connection and bridge
"""
import requests
import time
from config import TELEGRAM_BOT_TOKEN, BRIDGE_URL

print("=" * 60)
print("🔍 DIAGNOSTIC TEST FOR TELEGRAM BOT")
print("=" * 60)

# Test 1: Direct Telegram API
print("\n📡 Test 1: Direct Telegram API")
try:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    print(f"URL: {url}")
    r = requests.get(url, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"✅ SUCCESS: {r.json()['result']['username']}")
    else:
        print(f"❌ FAILED: {r.text}")
except Exception as e:
    print(f"❌ ERROR: {e}")

# Test 2: Bridge URL
print("\n🌉 Test 2: Bridge URL Health")
try:
    print(f"Bridge: {BRIDGE_URL}")
    r = requests.get(BRIDGE_URL, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print("✅ Bridge is accessible")
    else:
        print(f"⚠️ Bridge returned {r.status_code}")
except Exception as e:
    print(f"❌ Bridge ERROR: {e}")

# Test 3: Bridge -> Telegram
print("\n🌉➡️📡 Test 3: Telegram via Bridge")
try:
    url = f"{BRIDGE_URL}/bot{TELEGRAM_BOT_TOKEN}/getMe"
    print(f"URL: {url}")
    r = requests.get(url, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(f"✅ SUCCESS via Bridge: {r.json()['result']['username']}")
    else:
        print(f"❌ FAILED: {r.text}")
except Exception as e:
    print(f"❌ ERROR: {e}")

# Test 4: Internet connectivity
print("\n🌐 Test 4: General Internet")
try:
    r = requests.get("https://www.google.com", timeout=5)
    print(f"Google: {r.status_code} ✅")
except Exception as e:
    print(f"Google: ❌ {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
