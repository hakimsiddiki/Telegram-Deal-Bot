---
title: Amazon Deal Bot
emoji: 🛒
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
python_version: 3.11
app_file: app.py
pinned: false
---

# 🤖 Amazon Deal Telegram Bot — Complete Setup Guide

## 📁 Files
```
amazon_deal_bot/
├── app.py        ← Main bot code (chherna nahi)
├── config.py     ← Sirf YEH file edit karein
├── requirements.txt
└── README.md     ← Ye file
```

Bot ab bahut saare bestseller categories se deals scrape karta hai –
Luxury Beauty se lekar Amazon Fresh, Fashion, Electronics, Sports, Books,
Aur bhi bahut kuch. Sirf "best seller" pages se hi deals nikaali jaati hain.

---

## ✅ Step 1 — Python Install Karein
Python 3.10+ chahiye.
```
python --version
```

---

## ✅ Step 2 — Libraries Install Karein
```bash
pip install python-telegram-bot requests beautifulsoup4 lxml fake-useragent schedule
```

---

## ✅ Step 3 — Telegram Bot Banayein (@BotFather)

1. Telegram mein `@BotFather` open karein
2. `/newbot` type karein
3. Bot ka naam dein (e.g. "Amazon Deals India")
4. Username dein (e.g. `AmazonDealsIndia_bot`)
5. **Token copy karein** → config.py mein `TELEGRAM_BOT_TOKEN` mein paste karein

---

## ✅ Step 4 — Chat ID Pata Karein

### Channel ke liye:
1. Apna channel banayein (public ya private)
2. Bot ko channel ka **Admin** banayein
3. `TELEGRAM_CHAT_ID = "@your_channel_username"` set karein

### Group ke liye:
1. Bot ko group mein add karein
2. `@userinfobot` ko group mein add karein — woh group ID batayega
3. `TELEGRAM_CHAT_ID = "-100xxxxxxxxxx"` set karein

### Sirf aapko bhejne ke liye:
1. `@userinfobot` se apna user ID pata karein
2. `TELEGRAM_CHAT_ID = "123456789"` set karein

---

## ✅ Step 5 — Affiliate Tag Set Karein

1. [Amazon Associates](https://affiliate-program.amazon.in) login karein
2. **Performance → Manage Tracking IDs** → apna tag copy karein
3. config.py mein `AFFILIATE_TAG = "yourtag-21"` set karein

---

## ✅ Step 6 — config.py Fill Karein

```python
TELEGRAM_BOT_TOKEN  = "7123456789:AAFxxxxxxxxxxxxxxxxxxxxx"
TELEGRAM_CHAT_ID    = "@mydealsChannel"
AFFILIATE_TAG       = "myblog-21"
AMAZON_COUNTRY      = "in"          # in / us / uk
SCRAPE_INTERVAL_MINUTES = 30          # ek deal ke baad 30 min tak rukega
DEALS_PER_RUN       = 5             # ek baar mein 5 deals
```

---

## ✅ Step 7 — Bot Chalayein

```bash
python app.py
```

Bot chalate hi ek cycle karega (ek deal post ho sakta hai) aur phir `SCRAPE_INTERVAL_MINUTES` mein defined gap ke baad next cycle start karega (default 30 minutes).

---

## 🔄 24/7 Run Karne Ke Options

### Option A — Screen (Linux/Mac/VPS)
```bash
screen -S dealbot
python app.py
# Ctrl+A phir D se detach karein
```

### Option B — Systemd Service (Linux VPS)
```ini
# /etc/systemd/system/dealbot.service
[Unit]
Description=Amazon Deal Telegram Bot
After=network.target

[Service]
WorkingDirectory=/path/to/amazon_deal_bot
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable dealbot
sudo systemctl start dealbot
```

### Option C — Free Hosting
- **Railway.app** (free tier mein chalega)
- **Render.com** (background worker)
- **Google Cloud Run** (free credits)

---

## 📱 Sample Message (Bot Kuch Aisa Bhejega)

Bot ab product ki **image ke saath** bhi post karega (agar page se scrape ho jaye); abhi multiple HTML attributes
(seperti `data-a-dynamic-image`, `srcset`, etc.) check kiye jaate hain taki sahi high‑res photo mil sake.

> **Tip:** Telegram kuch photos (e.g. undergarments) ko auto‑blur karta hai. Agar aap blur se pareshaan ho,
> environment variable `SEND_IMAGE_AS_DOCUMENT=1` set kar den — is se image file document ki tarah bheji
> jaayegi, jisse blur nahi hoga.  Log mein aap dekhenge `📸 Image URL:` se scraped URL bhi milegi.

```
🛒 boAt Rockerz 255 Pro+ Bluetooth Wireless Earphones

💰 Price: ₹1,499  |  🔥 50% OFF

⭐ Rating: 4.1 / 5 ⭐ (2,34,567 ratings)

📝 Description:
 • 40 Hours Battery Life with Type-C fast charging
 • IPX5 Water & Sweat Resistant
 • Dual Equalizer Mode

🕒 Deal Time: 17 Feb 2025, 03:30 PM

🔗 Buy Now (Affiliate Link):
https://www.amazon.in/dp/B08XYZ1234?tag=myblog-21

━━━━━━━━━━━━━━━━━━━━
💡 Links contain affiliate tag. Happy Shopping! 🛍️
```

---

## ⚠️ Important Notes

| Baat | Details |
|------|---------|
| Scraping TOS | Amazon ki Terms of Service mein scraping allowed nahi hai — personal use ke liye theek hai, commercial scale par risk hai |
| Rate Limiting | Code mein random delays hain taaki ban na ho |
| IP Ban | Zyada quickly mat chalayein — interval 4-6 ghante rakhen |
| Better Option | Scale karna ho to **Amazon Product Advertising API** (PA-API) use karein — woh official hai |

---

## 🆘 Common Errors

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError` | `pip install -r requirements.txt` chalayein |
| `Unauthorized` | Bot token galat hai |
| `Chat not found` | Bot ko channel/group ka admin banayein |
| `0 deals found` | Amazon ne block kiya — kuch ghante baad try karein |

---

*Bot made with ❤️ using Python + python-telegram-bot + BeautifulSoup*