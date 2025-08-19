# -*- coding: utf-8 -*-
import os, asyncio, logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

BANTIN_FILE = "bantin/ban_tin.pdf"
TIMEOUT = 25_000  # ms

os.makedirs("tools", exist_ok=True)
logging.basicConfig(
    filename="tools/uploader.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# === CẦN CHỈNH THEO DOM THẬT ===
SEL = {
    "username": "#txtUserName",
    "password": "#txtPassword",
    "login_btn": "#btnLogin",
    # "menu_upload": "a[href*='frmGSMonth_ByCenterForecast.aspx']",  # nếu cần bấm menu
    "file_input": "input[type='file']",
    "submit_btn": "#btnUpload",
    "result_area": "#lblResult"
}

async def main():
    load_dotenv()
    url = os.getenv("PORTAL_URL")
    user = os.getenv("USERNAME")
    pw   = os.getenv("PASSWORD")
    if not url or not user or not pw:
      raise SystemExit("Thiếu PORTAL_URL/USERNAME/PASSWORD (Secrets).")
    if not os.path.isfile(BANTIN_FILE):
      raise SystemExit(f"Không thấy file: {BANTIN_FILE}")

    logging.info("=== Bắt đầu upload bằng Playwright ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width":1280,"height":800})
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT)
            await page.fill(SEL["username"], user, timeout=TIMEOUT)
            await page.fill(SEL["password"], pw, timeout=TIMEOUT)
            await page.click(SEL["login_btn"], timeout=TIMEOUT)
            await page.wait_for_timeout(3000)

            # nếu cần bấm menu để đến form upload:
            # await page.click(SEL["menu_upload"], timeout=TIMEOUT)
            # await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)

            await page.set_input_files(SEL["file_input"], BANTIN_FILE, timeout=TIMEOUT)
            await page.click(SEL["submit_btn"], timeout=TIMEOUT)
            await page.wait_for_timeout(5000)

            try:
                txt = await page.text_content(SEL["result_area"], timeout=3000)
                logging.info(f"Kết quả: {txt}")
            except PWTimeout:
                logging.warning("Không thấy vùng kết quả; đã chụp ảnh.")

            await page.screenshot(path="after_upload.png", full_page=True)
        except Exception as e:
            logging.exception(f"Lỗi upload: {e}")
            await page.screenshot(path="after_upload.png", full_page=True)
            raise
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
