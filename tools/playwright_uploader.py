# -*- coding: utf-8 -*-
import os, re, asyncio, logging
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

TIMEOUT = 30_000  # ms
BANTIN_DIR = Path("bantin")

# Log
os.makedirs("tools", exist_ok=True)
logging.basicConfig(
    filename="tools/uploader.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

LOGIN_URL  = os.getenv("PORTAL_URL") or os.getenv("PORTAL_LOGIN_URL") or "http://222.255.11.117:8888/Login.aspx"
UPLOAD_URL = os.getenv("UPLOAD_URL") or "http://222.255.11.117:8888/UploadFile.aspx"

DATE_RE = re.compile(r"(20\d{6})(?:[_-]?(\d{4}))?")  # YYYYMMDD + optional HHMM

def score_by_name(p: Path) -> int:
    """
    Tính điểm để sắp xếp theo ngày trong tên file.
    Ưu tiên YYYYMMDDHHMM nếu có; fallback YYYYMMDD; fallback 0.
    """
    m = DATE_RE.search(p.name)
    if not m:
        return 0
    yyyymmdd = int(m.group(1))
    hhmm = int(m.group(2)) if m.group(2) else 0
    return yyyymmdd * 10000 + hhmm

def pick_latest_files() -> tuple[Path, Path | None]:
    """
    Chọn file bản tin & hồ sơ trong thư mục bantin/ theo quy ước:
    - Hồ sơ: tên bắt đầu bằng 'HS' hoặc chứa '_HS' (không phân biệt hoa thường)
    - Bản tin: còn lại.
    - Nếu không tìm thấy hồ sơ -> để None (sau đó sẽ dùng lại bản tin).
    """
    if not BANTIN_DIR.exists():
        raise SystemExit("Chưa có thư mục 'bantin/'. Hãy upload file vào đó.")

    pdfs = [p for p in BANTIN_DIR.glob("*.pdf") if p.is_file()]
    if not pdfs:
        raise SystemExit("Không tìm thấy file PDF nào trong 'bantin/'.")

    def is_hoso(p: Path) -> bool:
        n = p.name.lower()
        return n.startswith("hs") or "_hs" in n

    hoso_list = [p for p in pdfs if is_hoso(p)]
    bantin_list = [p for p in pdfs if not is_hoso(p)]

    bantin = max(bantin_list, key=score_by_name, default=None)
    hoso = max(hoso_list, key=score_by_name, default=None)

    # Nếu vẫn không xác định được "bản tin", lấy PDF có điểm cao nhất bất kể tên
    if bantin is None:
        bantin = max(pdfs, key=score_by_name)

    logging.info(f"Chọn BẢN TIN: {bantin.name}")
    if hoso:
        logging.info(f"Chọn HỒ SƠ : {hoso.name}")
    else:
        logging.info("Không có HỒ SƠ riêng -> sẽ dùng lại file BẢN TIN cho input thứ 2.")
    return bantin, hoso

async def login(page, username, password):
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    user_in = page.locator('input[type="text"], input[type="email"]').first
    pass_in = page.locator('input[type="password"]').first
    await user_in.fill(username, timeout=TIMEOUT)
    await pass_in.fill(password, timeout=TIMEOUT)

    try:
        await page.getByRole("button", name=lambda s: "đăng nhập" in s.lower()).click(timeout=5000)
    except Exception:
        await page.locator("button:has-text('Đăng nhập'), input[type=submit][value*='Đăng nhập']").first.click(timeout=TIMEOUT)

    await page.wait_for_timeout(2500)

async def upload_file(page, bantin_path: Path, hoso_path: Path | None):
    await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    # Nếu cần chọn dropdown, thêm ở đây (đã để mặc định nên em tạm bỏ qua).
    # Ví dụ:
    # selects = page.locator("select")
    # try:
    #     await selects.nth(0).select_option(label="Quảng Trị")
    #     await selects.nth(1).select_option(label="Khí tượng thủy văn Bình thường")
    #     await selects.nth(2).select_option(label="Thời tiết điểm đến 10 ngày")
    #     await selects.nth(3).select_option(label="Thời tiết điểm đến 10 ngày")
    # except Exception:
    #     pass

    file_inputs = page.locator('input[type="file"]')
    count = await file_inputs.count()
    if count < 1:
        raise RuntimeError("Không tìm thấy input type=file trên trang Upload.")

    # Input 1: Bản tin
    await file_inputs.nth(0).set_input_files(str(bantin_path), timeout=TIMEOUT)

    # Input 2: Hồ sơ (nếu có), nếu không thì dùng lại bản tin
    if count >= 2:
        await file_inputs.nth(1).set_input_files(str(hoso_path or bantin_path), timeout=TIMEOUT)

    # Bấm Upload
    try:
        await page.getByRole("button", name=lambda s: s.strip().lower() == "upload").click(timeout=5000)
    except Exception:
        await page.locator("button:has-text('Upload'), input[type=submit][value*='Upload']").first.click(timeout=TIMEOUT)

    await page.wait_for_timeout(5000)
    await page.screenshot(path="after_upload.png", full_page=True)

async def main():
    load_dotenv()
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    if not username or not password:
        raise SystemExit("Thiếu USERNAME/PASSWORD (Secrets).")

    bantin, hoso = pick_latest_files()

    logging.info("=== Bắt đầu upload ===")
    logging.info(f"Login URL : {LOGIN_URL}")
    logging.info(f"Upload URL: {UPLOAD_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await login(page, username, password)
            await upload_file(page, bantin, hoso)
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
