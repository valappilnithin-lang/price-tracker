import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Example product list
products = [
    {"name": "Airpods", "url": "https://www.amazon.in/dp/PRODUCT_ID"},
    {"name": "Pixel", "url": "https://www.flipkart.com/item-url"}
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

async def fetch_price(page, product, retries=3):
    for attempt in range(retries):
        try:
            await page.goto(product["url"], timeout=30000)
            
            # Wait for price element (Amazon example)
            price_element = await page.wait_for_selector("span.a-price-whole", timeout=15000)
            price = await price_element.inner_text()
            print(f"✅ {product['name']} price: {price}")
            return price

        except PlaywrightTimeoutError:
            print(f"⚠️ Timeout fetching {product['name']} (Attempt {attempt+1}/{retries})")
        except Exception as e:
            print(f"⚠️ Error fetching {product['name']} (Attempt {attempt+1}/{retries}): {e}")
        
        # Small random delay before retry
        await asyncio.sleep(2 + attempt)

    print(f"❌ Failed to fetch price for {product['name']}")
    return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        for product in products:
            await fetch_price(page, product)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
