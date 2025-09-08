# -*- coding: utf-8 -*-
import os
import re
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ===== Cấu hình chung =====
TIMEOUT = 60_000  # ms (tăng từ 30s lên 60s cho ổn định)
BANTIN_DIR = Path("bantin")

# Log file
os.makedirs("tools", exist_ok=True)
logging.basicConfig(
    filename="tools/uploader.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# URL & Secrets
LOGIN_URL  = os.getenv("PORTAL_URL") or os.getenv("PORTAL_LOGIN_URL") or "http://222.255.11.117:8888/Login.aspx"
UPLOAD_URL = os.getenv("UPLOAD_URL") or "http://222.255.11.117:8888/UploadFile.aspx"

# (Tuỳ chọn) label cho dropdown – đặt qua Secrets nếu cần
UNIT_LABEL = os.getenv("UNIT_LABEL")  # ví dụ: "Đài KTTV Nghệ An"
DOC_LABEL  = os.getenv("DOC_LABEL")   # ví dụ: "Khí tượng thủy văn Bình thường"
CAT1_LABEL = os.getenv("CAT1_LABEL")  # ví dụ: "Thời tiết điểm đến 10 ngày"
CAT2_LABEL = os.getenv("CAT2_LABEL")  # ví dụ: "Thời tiết điểm đến 10 ngày"

# Regex lấy ngày từ tên file: YYYYMMDD + (tuỳ chọn) _HHMM
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
    - Hồ sơ: tên chứa 'HS' (không phân biệt hoa/thường), ví dụ: HS_..., ..._HS_...
    - Bản tin: còn lại.
    - Nếu không tìm thấy hồ sơ -> trả None (KHÔNG dùng lại bản tin).
    """
    if not BANTIN_DIR.exists():
        raise SystemExit("Chưa có thư mục 'bantin/'. Hãy upload file PDF vào đó.")

    pdfs = [p for p in BANTIN_DIR.glob("*.pdf") if p.is_file()]
    if not pdfs:
        raise SystemExit("Không tìm thấy file PDF nào trong 'bantin/'.")

    def is_hoso(p: Path) -> bool:
        return "hs" in p.name.lower()

    hoso_list = [p for p in pdfs if is_hoso(p)]
    bantin_list = [p for p in pdfs if not is_hoso(p)]

    bantin = max(bantin_list, key=score_by_name, default=None)
    hoso = max(hoso_list, key=score_by_name, default=None)

    if bantin is None:
        # Nếu không xác định được "bản tin", lấy PDF có điểm cao nhất bất kể tên
        bantin = max(pdfs, key=score_by_name)

    logging.info(f"Chọn BẢN TIN: {bantin.name}")
    if hoso:
        logging.info(f"Chọn HỒ SƠ : {hoso.name}")
    else:
        logging.info("Không có HỒ SƠ riêng -> sẽ chỉ upload file BẢN TIN.")
    return bantin, hoso

async def login(page, username, password):
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    user_in = page.locator('input[type="text"], input[type="email"]').first
    pass_in = page.locator('input[type="password"]').first
    await user_in.fill(username, timeout=TIMEOUT)
    await pass_in.fill(password, timeout=TIMEOUT)

    # Bấm nút Đăng nhập (ưu tiên get_by_role + regex)
    import re as _re
    try:
        await page.get_by_role("button", name=_re.compile(r"đăng\s*nhập", _re.I)).click(timeout=TIMEOUT)
    except Exception:
        await page.locator("button:has-text('Đăng nhập'), input[type=submit][value*='Đăng nhập']").first.click(timeout=TIMEOUT)

    # chờ form xử lý
    await page.wait_for_timeout(1500)

async def maybe_select_dropdowns(page):
    """
    Nếu trang yêu cầu chọn dropdown theo đơn vị/loại tài liệu/chuyên mục,
    có thể cấu hình qua Secrets (UNIT_LABEL/DOC_LABEL/CAT1_LABEL/CAT2_LABEL).
    Bỏ qua nếu không đặt.
    """
    if not any([UNIT_LABEL, DOC_LABEL, CAT1_LABEL, CAT2_LABEL]):
        return
    selects = page.locator("select")
    try:
        idx = 0
        if UNIT_LABEL:
            await selects.nth(idx).select_option(label=UNIT_LABEL); idx += 1
        if DOC_LABEL:
            await selects.nth(idx).select_option(label=DOC_LABEL); idx += 1
        if CAT1_LABEL:
            await selects.nth(idx).select_option(label=CAT1_LABEL); idx += 1
        if CAT2_LABEL:
            await selects.nth(idx).select_option(label=CAT2_LABEL); idx += 1
        await page.wait_for_timeout(500)  # cho postback/dropdown ổn định
        logging.info("Đã chọn dropdown theo Secrets (nếu có).")
    except Exception as e:
        logging.info(f"Dropdown có thể không cần hoặc index khác: {e}")

async def upload_file(page, bantin_path: Path, hoso_path: Path | None):
    await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=TIMEOUT)

    # Chọn dropdown nếu cần
    await maybe_select_dropdowns(page)

    # Tìm các input file (1: bản tin; 2: hồ sơ)
    file_inputs = page.locator('input[type="file"]')
    count = await file_inputs.count()
    if count < 1:
        raise RuntimeError("Không tìm thấy input type=file trên trang Upload.")

    # Input 1: Bản tin (bắt buộc)
    await file_inputs.nth(0).set_input_files(str(bantin_path), timeout=TIMEOUT)

    # Input 2: Hồ sơ — CHỈ đặt khi thật sự có file HS
    if count >= 2 and hoso_path:
        await file_inputs.nth(1).set_input_files(str(hoso_path), timeout=TIMEOUT)
    else:
        logging.info("Không có file HS hoặc trang chỉ có 1 input — chỉ upload bản tin.")

    # Bắt dialog (alert/confirm) nếu có sau khi upload
    page.once("dialog", lambda d: (logging.info(f"Dialog: {d.message}"), d.accept()))

    # Bấm Upload nhưng KHÔNG chờ điều hướng (ASP.NET postback hay treo)
    clicked = False
    selectors = [
        "#cphContent_Button1",                       # ID thường thấy ở nút Upload
        "input[type=submit][value*='Upload']",       # input submit
        "button:has-text('Upload')"                  # button text
    ]
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=TIMEOUT, no_wait_after=True)
            logging.info(f"Clicked upload by selector: {sel}")
            clicked = True
            break
        except Exception as e:
            logging.warning(f"Try click {sel} failed: {e}")

    if not clicked:
        raise RuntimeError("Không bấm được nút Upload bằng các selector đã thử.")

    # Chủ động chờ mạng yên thay vì chờ "scheduled navigation"
    try:
        await page.wait_for_load_state("networkidle", timeout=60_000)
    except Exception:
        await page.wait_for_timeout(5000)

    await page.screenshot(path="after_upload.png", full_page=True)
    logging.info("Chụp after_upload.png sau Upload")

async def main():
    load_dotenv()
    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    if not username or not password:
        raise SystemExit("Thiếu USERNAME/PASSWORD (Secrets).")

    bantin, hoso = pick_latest_files()

    logging.info("=== Bắt đầu upload (Nghệ An) ===")
    logging.info(f"Login URL : {LOGIN_URL}")
    logging.info(f"Upload URL: {UPLOAD_URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await login(page, username, password)
            await upload_file(page, bantin, hoso)
            logging.info("Hoàn tất. Xem after_upload.png + tools/uploader.log để xác nhận.")
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
