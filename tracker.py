import os
import json
import csv
from datetime import datetime
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load .env (for local use only, not needed in GitHub Actions)
load_dotenv()

# Secrets from environment (never hardcode!)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LOG_FILE = "price_log.csv"

def send_telegram(message):
    """Send Telegram message securely via bot API"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram config missing, skipping message")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
        print(f"[DEBUG] Telegram response {r.status_code}")
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")

def fetch_price(page, url):
    """Open product page and extract price"""
    page.goto(url, timeout=60000)
    # Try Flipkart
    price_tag = page.query_selector("div._30jeq3._16Jk6d")
    if not price_tag:
        # Try Amazon
        price_tag = page.query_selector("span.a-price-whole")
    if price_tag:
        text = price_tag.inner_text().strip()
        digits = "".join(c for c in text if c.isdigit())
        return int(digits) if digits else None
    return None

def run_tracker():
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    with sync_playwright() as p:
        # Decide headless mode from env
        headless_flag = os.getenv("RUN_HEADLESS", "true").lower() in ("1", "true", "yes")
        browser = p.chromium.launch(
            headless=headless_flag,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = browser.new_page()

        for product in cfg.get("products", []):
            name = product["name"]
            url = product["url"]
            target = product.get("target_price")

            print(f"[CHECK] {name}")
            price = fetch_price(page, url)
            print(f"[DEBUG] Price = {price}")

            if price:
                ts = datetime.utcnow().isoformat()
                with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([ts, product["id"], name, price])

                if target and price <= target:
                    msg = f"📉 Price drop: {name} now ₹{price} (target {target})\n{url}"
                    send_telegram(msg)

        browser.close()

if __name__ == "__main__":
    send_telegram("✅ Test message from GitHub Actions")
    run_tracker()
