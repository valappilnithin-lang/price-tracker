import os
import json
import asyncio
import logging
import requests
from playwright.async_api import async_playwright

# --- Logging setup ---
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s] %(message)s"
)

# --- Secrets from environment ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TELEGRAM_TOKEN or not CHAT_ID:
    logging.error("❌ TELEGRAM_TOKEN or CHAT_ID not set in environment!")
    exit(1)

# --- Load product list from config.json ---
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    logging.error(f"❌ {CONFIG_FILE} not found! Did you decode it from secret?")
    exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    try:
        config = json.load(f)
        products = config.get("products", [])
    except Exception as e:
        logging.error(f"❌ Failed to load {CONFIG_FILE}: {e}")
        exit(1)

# --- Telegram helper ---
def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logging.error(f"❌ Telegram send failed: {resp.text}")
    except Exception as e:
        logging.error(f"❌ Telegram exception: {e}")

# --- Scraper ---
async def check_prices():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for product in products:
            name = product.get("name", "Unknown")
            url = product.get("url")
            target = product.get("target_price")

            if not url:
                logging.warning(f"⚠️ No URL for {name}, skipping.")
                continue

            logging.info(f"🔎 Checking: {name}")
            try:
                await page.goto(url, timeout=60000)
                # Adjust selector depending on site (Amazon India example)
                price_el = await page.locator("span.a-price-whole").first
                price_text = await price_el.inner_text(timeout=30000)

                logging.debug(f"[DEBUG] Raw price text: {price_text}")
                clean_price = int("".join([c for c in price_text if c.isdigit()]))

                if clean_price:
                    logging.info(f"💰 {name}: ₹{clean_price} (Target: ₹{target})")

                    if target and clean_price <= target:
                        send_telegram_message(
                            f"✅ Price drop!\n{name}\nNow: ₹{clean_price}\nTarget: ₹{target}\n{url}"
                        )
                    else:
                        logging.info(f"ℹ️ No alert for {name} yet.")
                else:
                    logging.warning(f"⚠️ Could not parse price for {name}")

            except Exception as e:
                logging.error(f"❌ Error checking {name}: {e}")

        await browser.close()


if __name__ == "__main__":
    logging.info("🚀 Tracker script started")
    asyncio.run(check_prices())
    logging.info("🏁 Tracker script finished")
