import asyncio
import json
import logging
import os
import requests
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SESSION = os.getenv("SESSION")
COOKIES = os.getenv("COOKIES")


# --- Telegram sender ---
def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.warning("⚠️ TELEGRAM_TOKEN or CHAT_ID not set, skipping Telegram")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": message})
        if resp.status_code != 200:
            logging.error(f"Telegram error: {resp.text}")
    except Exception as e:
        logging.error(f"Telegram exception: {e}")


# --- Extract price text ---
async def get_price_text(page, url):
    if "amazon" in url.lower():
        selectors = [
            "span.a-price-whole",
            "span.a-offscreen",
            "span.priceBlockBuyingPriceString",
            "span#priceblock_ourprice",
            "span#priceblock_dealprice"
        ]
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, timeout=6000)
                price_el = page.locator(sel).first
                text = await price_el.inner_text()
                if text:
                    # If whole+fraction both exist
                    if sel == "span.a-price-whole":
                        try:
                            frac = await page.locator("span.a-price-fraction").first.inner_text(timeout=2000)
                            text = f"₹{text}{frac}"
                        except:
                            text = f"₹{text}"
                    logging.info(f"[DEBUG] Amazon price found via {sel}: {text}")
                    return text.strip()
            except Exception:
                continue

    elif "flipkart" in url.lower():
        selectors = [
            "div._30jeq3",
            "div._16Jk6d",
            "span._30jeq3",
            "text=₹"
        ]
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, timeout=6000)
                price_el = page.locator(sel).first
                text = await price_el.inner_text()
                if text:
                    logging.info(f"[DEBUG] Flipkart price found via {sel}: {text}")
                    return text.strip()
            except Exception:
                continue

    return None


# --- Core fetch ---
async def get_price(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Add cookies from secrets if provided
        if COOKIES:
            try:
                cookies = json.loads(COOKIES)
                await context.add_cookies(cookies)
                logging.info("[INFO] Cookies loaded from secrets")
            except Exception as e:
                logging.warning(f"[WARN] Invalid cookies: {e}")

        page = await context.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        })

        await page.goto(url, timeout=60000, wait_until="networkidle")

        price_text = await get_price_text(page, url)

        await browser.close()
        return price_text


# --- Runner ---
async def main():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        logging.error("❌ config.json not found")
        return

    for product in config.get("products", []):
        url = product.get("url")
        name = product.get("name")
        target = product.get("target_price")

        if not url:
            continue

        price_text = await get_price(url)

        if price_text:
            msg = f"✅ {name}: {price_text} (Target: {target})"
            print(msg)
            send_telegram_message(msg)
        else:
            msg = f"⚠️ Could not fetch price for {name}"
            print(msg)
            send_telegram_message(msg)


if __name__ == "__main__":
    asyncio.run(main())
