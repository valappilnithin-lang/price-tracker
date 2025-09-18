#!/usr/bin/env python3
"""
tracker.py - Playwright price tracker with Telegram alerts

Usage:
  python tracker.py record   # opens browser, loads config URLs, lets you interact, then saves state.json
  python tracker.py run      # run using saved state.json (if present)
"""

import sys
import json
import csv
import os
import time
import random
import re
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import requests

print("[DEBUG] tracker.py started with args:", sys.argv)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "state.json"
SCREENSHOT_DIR = "screenshots"
LOG_FILE = "price_log.csv"

# ---------------- Notifications ---------------- #
def send_telegram(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10
            )
            print(f"[DEBUG] Telegram response: {r.status_code}")
        except Exception as e:
            print(f"[ERROR] Telegram send failed: {e}")
    else:
        print("[DEBUG] Telegram not configured.")

# ---------------- Utils ---------------- #
def ensure_dirs():
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "id", "name", "price"])

# ---------------- Scraper ---------------- #
def fetch_price_playwright(page, url, product_id):
    print(f"[DEBUG] Visiting: {url}")
    try:
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
    except PWTimeout:
        print("[WARN] Navigation timeout; continuing...")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    screenshot_file = os.path.join(SCREENSHOT_DIR, f"{product_id}_{ts}.png")
    try:
        page.screenshot(path=screenshot_file, full_page=True)
        print(f"[DEBUG] Screenshot saved: {screenshot_file}")
    except Exception as e:
        print(f"[WARN] Could not save screenshot: {e}")

    page.wait_for_timeout(1500)

    url_l = url.lower()
    price_candidate = None

    if "flipkart" in url_l:
        selectors = [
            "div._30jeq3._16Jk6d",
            "div._30jeq3",
            "div._25b18c",
            "span._2dXhWJ",
        ]
    elif "amazon." in url_l:
        selectors = [
            "span.a-price-whole",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "span#priceblock_saleprice",
            "span.a-offscreen"
        ]
    else:
        selectors = ["span.price", "div.price", "p.price"]

    # try selectors
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            txt = loc.first.inner_text(timeout=3000).strip()
            print(f"[DEBUG] Selector {sel} text: {txt!r}")
            digits = "".join(ch for ch in txt if ch.isdigit())
            if digits:
                price_candidate = int(digits)
                print(f"[DEBUG] Parsed price {price_candidate}")
                return price_candidate
        except Exception as e:
            print(f"[DEBUG] Selector {sel} error: {e}")
            continue

    # fallback regex
    try:
        content = page.content()
        m = re.search(r"(₹|&#8377;)\s*([\d,]+)", content)
        if m:
            digits = "".join(ch for ch in m.group(2) if ch.isdigit())
            if digits:
                price_candidate = int(digits)
                print(f"[DEBUG] Regex parsed price {price_candidate}")
                return price_candidate
    except Exception as e:
        print(f"[DEBUG] Regex fallback error: {e}")

    print("[DEBUG] All extraction attempts failed; returning None")
    return None

# ---------------- Workflows ---------------- #
def interactive_record_flow():
    print("[INFO] Starting interactive record flow.")
    with sync_playwright() as p:
        print("[DEBUG] Playwright context created.")
        browser = p.chromium.launch(headless=False, slow_mo=200,
                                    args=["--disable-blink-features=AutomationControlled"])
        print("[DEBUG] Chromium launched.")
        context = browser.new_context(viewport={"width":1366,"height":768}, locale="en-IN")
        page = context.new_page()
        print("[DEBUG] New page opened.")

        # load products
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for product in cfg.get("products", []):
            print(f"[INFO] Opening {product['name']} at {product['url']}")
            page.goto(product["url"])
            time.sleep(3)

        input("Press ENTER in terminal to save state.json...")
        context.storage_state(path=STATE_FILE)
        print(f"[INFO] Saved storage state to {STATE_FILE}")
        browser.close()

def run_flow():
    print("[INFO] Starting run flow.")
    ensure_dirs()
    with sync_playwright() as p:
        print("[DEBUG] Playwright context created.")
        browser = p.chromium.launch(headless=False,
                                    args=["--disable-blink-features=AutomationControlled"])
        print("[DEBUG] Chromium launched.")
        if os.path.exists(STATE_FILE):
            print(f"[DEBUG] Using {STATE_FILE}")
            context = browser.new_context(storage_state=STATE_FILE,
                                          viewport={"width":1366,"height":768}, locale="en-IN")
        else:
            print("[DEBUG] No state.json found, fresh context")
            context = browser.new_context(viewport={"width":1366,"height":768}, locale="en-IN")

        page = context.new_page()
        print("[DEBUG] New page opened.")

        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)

        for product in cfg.get("products", []):
            pid = product["id"]
            name = product["name"]
            url = product["url"]
            target = product.get("target_price")
            print(f"\n[CHECK] {name}")

            price = fetch_price_playwright(page, url, pid)
            print(f"[DEBUG] Fetched price: {price}")

            if price is not None:
                ts = datetime.utcnow().isoformat()
                with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([ts, pid, name, price])
                print(f"[LOG] {name} logged at ₹{price}")

                if target and price <= target:
                    msg = f"Price alert: {name} is now ₹{price} (target {target})\n{url}"
                    print("[ALERT] Sending Telegram notification.")
                    send_telegram(msg)
            else:
                print(f"[WARN] Could not extract price for {name}. See screenshot.")

        context.close()
        browser.close()
        print("[INFO] Run flow completed.")

# ---------------- Entry ---------------- #
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tracker.py [record|run]")
        sys.exit(1)

    mode = sys.argv[1].lower()
    if mode == "record":
        interactive_record_flow()
    elif mode == "run":
        run_flow()
    else:
        print("Unknown mode. Use record or run.")
