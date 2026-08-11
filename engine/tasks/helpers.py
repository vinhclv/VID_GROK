import random
from playwright.async_api import Page, Locator

async def human_click(locator: Locator, page: Page, force: bool = False):
    """
    Mô phỏng click chuột của người thật bằng Virtual Mouse.
    Không chiếm chuột vật lý của máy tính.
    """
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
        await locator.hover(timeout=5000)
        await page.wait_for_timeout(random.uniform(100, 300))
        await locator.click(delay=random.randint(50, 150), force=force)
    except Exception as e:
        await locator.click(delay=random.randint(50, 150), force=True)

async def human_type(locator: Locator, text: str, page: Page):
    """
    Mô phỏng gõ phím theo cụm (chunk) với tốc độ và nhịp thở của người thật.
    Tự động lọc bỏ ký tự '@' nếu gặp phải để tránh nạp các menu popup autocomplete.
    """
    clean_text = text.replace("@", "") if text else ""
    if not clean_text:
        return

    await human_click(locator, page)
    await page.wait_for_timeout(random.uniform(200, 400))
    idx = 0
    while idx < len(clean_text):
        chunk_size = random.randint(15, 30)
        chunk = clean_text[idx:idx + chunk_size]
        await locator.press_sequentially(chunk, delay=random.randint(5, 10))
        idx += chunk_size
        await page.wait_for_timeout(random.uniform(20, 50))
        if random.random() < 0.05:
            await page.wait_for_timeout(random.uniform(100, 200))
    await page.wait_for_timeout(random.uniform(200, 400))
