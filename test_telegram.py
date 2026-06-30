"""
Quick test script to verify Telegram bot can send messages
Run this to test if your bot token and chat ID are working
"""
import requests
import sys

# Bot configuration
BOT_TOKEN = "8306899550:AAF--2j7HyZV_pMBKvfFAK_v9eSAcy5DbiQ"
CHAT_ID = "-1003830805941"

def test_bot():
    print("🧪 Testing Telegram Bot Connection...")
    print(f"Bot Token: {BOT_TOKEN[:20]}...")
    print(f"Chat ID: {CHAT_ID}")
    
    # Test 1: Get bot info
    print("\n📋 Test 1: Getting bot info...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            print(f"✅ Bot Name: @{bot_info['result']['username']}")
            print(f"✅ Bot ID: {bot_info['result']['id']}")
        else:
            print(f"❌ Failed to get bot info: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Test 2: Send a test message
    print("\n📝 Test 2: Sending test message...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "✅ Bot Test Successful!\n\nYour Amazon Deal Bot is configured correctly and can send messages to Telegram.",
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Test message sent successfully!")
            print("🎉 Your bot is working! Check your Telegram channel/group.")
            return True
        else:
            print(f"❌ Failed to send message: {response.status_code}")
            print(f"Response: {response.text}")
            
            # Common error explanations
            if "chat not found" in response.text.lower():
                print("\n⚠️ Error: Chat not found!")
                print("   - Make sure the bot is added to your channel/group")
                print("   - Check if CHAT_ID is correct")
                print("   - For channels, CHAT_ID should start with -100")
            elif "forbidden" in response.text.lower():
                print("\n⚠️ Error: Forbidden!")
                print("   - Bot doesn't have permission to send messages")
                print("   - Make sure bot is an admin in the channel/group")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_bot()
    sys.exit(0 if success else 1)
