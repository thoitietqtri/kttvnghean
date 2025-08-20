# -*- coding: utf-8 -*-
import os, asyncio, logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

BANTIN_FILE = "bantin/ban_tin.pdf"
TIMEOUT = 30_000  # ms

# Log
os.makedirs("tools", exist_ok=True)
logging.basicConfig(
    filename="tools/uploader.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# URL: có thể đặt bằng Secrets. Nếu không có sẽ dùng mặc định dưới
LOGIN_URL  = os.getenv("PORTAL_URL") or os.getenv("PORTAL_LOGIN_URL") or "http://222.255.11.117:8888/Login.aspx"
UPLOAD_URL = os.getenv("UPLOAD_URL") or "http://222.255.11.117:8888/UploadFile.aspx"

async def login(page, username, password):
    # Đi tới trang đăng nhập
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    # Ô tài khoản & mật khẩu (tổng quát: text/email + password)
    user_in = page.locator('input[type="text"], input[type="email"]').first
    pass_in = page.locator('input[type="password"]').first
    await user_in.fill(username, timeout=TIMEOUT)
    await pass_in.fill(password, timeout=TIMEOUT)

    # Nút "Đăng nhập" (ưu tiên theo text tiếng Việt)
    try:
        await page.getByRole("button", name=lambda s: "đăng nhập" in s.lower()).click(timeout=5000)
    except Exception:
        await page.locator("button:has-text('Đăng nhập'), input[type=submit][value*='Đăng nhập']").first.click(timeout=TIMEOUT)

    await page.wait_for_timeout(2500)  # đệm nhẹ

async def upload_file(page, file_path):
    if not os.path.isfile(file_path):
        raise SystemExit(f"Không thấy file: {file_path}")

    # Đến trang upload thẳng sau khi đăng nhập
    await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    # Trên trang có 2 input file: "Upload Bản tin Dự báo" và "Upload Hồ sơ dự báo"
    file_inputs = page.locator('input[type="file"]')
    count = await file_inputs.count()
    if count < 1:
        raise RuntimeError("Không tìm thấy input type=file trên trang Upload.")

    # Luôn set file cho input thứ nhất (Bản tin)
    await file_inputs.nth(0).set_input_files(file_path, timeout=TIMEOUT)

    # Nhiều nơi bắt buộc cả 2 → set luôn input thứ hai nếu có
    if count >= 2:
        try:
            await file_inputs.nth(1).set_input_files(file_path, timeout=TIMEOUT)
        except Exception:
            pass  # nếu không cần thì bỏ qua

    # Bấm nút Upload theo text
    try:
        await page.getByRole("button", name=lambda s: s.strip().lower() == "upload").click(timeout=5000)
    except Exception:
        await page.locator("button:has-text('Upload'), input[type=submit][value*='Upload']").first.click(timeout=TIMEOUT)

    # Chờ phản hồi & chụp ảnh làm bằng chứng
    await page.wait_for_timeout(5000)
    # Nếu có label kết quả thì log
    try:
        # thử tìm mọi nhãn có chữ "thành công", "không", "lỗi"...
        body_text = (await page.content()) or ""
        # Không parse chi tiết — chụp ảnh là chắc nhất
        logging.info("Đã bấm Upload, đang chụp ảnh bằng chứng…")
    except PWTimeout:
        logging.warning("Không đọc được nội dung sau Upload.")

    await page.screenshot(path="after_upload.png", full_page=True)

async def main():
    load_dotenv()
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    if not username or not password:
        raise SystemExit("Thiếu USERNAME/PASSWORD (Secrets).")

    if not os.path.isfile(BANTIN_FILE):
        raise SystemExit(f"Thiếu {BANTIN_FILE}. Hãy push file này trước khi chạy.")

    logging.info("=== Bắt đầu quy trình upload ===")
    logging.info(f"Login URL : {LOGIN_URL}")
    logging.info(f"Upload URL: {UPLOAD_URL}")
    logging.info(f"File      : {BANTIN_FILE}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await login(page, username, password)
            await upload_file(page, BANTIN_FILE)
            logging.info("Hoàn tất. Xem after_upload.png + uploader.log để xác nhận.")
        except Exception as e:
            logging.exception(f"Lỗi: {e}")
            try:
                await page.screenshot(path="after_upload.png", full_page=True)
            except Exception:
                pass
            raise
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
