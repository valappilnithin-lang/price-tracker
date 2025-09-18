import os
import json
import csv
from datetime import datetime
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load environment variables (for local runs)
load_dotenv()

# Secrets from environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LOG_FILE = "price_log.csv"


def send_telegram(message):
    """Send Telegram message via bot API"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram config missing, skipping message")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
        print(f"[DEBUG] Telegram response {r.status_code}")
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")


def fetch_price(page, url, product_id="unknown"):
    """Open product page, save screenshot, and extract price"""
    page.goto(url, timeout=60000)

    # save screenshot every run for debugging
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{product_id}.png"
    page.screenshot(path=screenshot_path)
    print(f"[DEBUG] Screenshot saved: {screenshot_path}")

    selectors = [
        "div._30jeq3._16Jk6d",              # Flipkart
        "span.a-price-whole",               # Amazon (normal)
        "span.a-price > span.a-offscreen",  # Amazon (alternate)
        "span#priceblock_ourprice",         # Amazon (old)
        "span#priceblock_dealprice"         # Amazon (deal)
    ]

    for sel in selectors:
        try:
            elem = page.query_selector(sel)
            if elem:
                text = elem.inner_text().strip()
                digits = "".join(c for c in text if c.isdigit())
                if digits:
                    return int(digits)
        except Exception as e:
            print(f"[DEBUG] Selector {sel} failed: {e}")

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
            pid = product["id"]
            name = product["name"]
            url = product["url"]
            target = product.get("target_price")

            print(f"[CHECK] {name}")
            price = fetch_price(page, url, pid)
            print(f"[DEBUG] Price = {price}")

            ts = datetime.utcnow().isoformat()

            # log to CSV even if None
            with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([ts, pid, name, price])

            if price:
                if target and price <= target:
                    msg = f"📉 Price drop: {name} now ₹{price} (target {target})\n{url}"
                    send_telegram(msg)
                else:
                    # Debug message: current price
                    send_telegram(f"ℹ️ {name} current price: ₹{price} (target {target})")
            else:
                send_telegram(f"⚠️ Could not fetch price for {name}\n{url}")

        browser.close()


if __name__ == "__main__":
    run_tracker()
