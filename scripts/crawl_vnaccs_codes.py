from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG
# ============================================================

START_URL = "https://www.customs.gov.vn/index.jsp?cid=1192&pageId=26"

OUTPUT_DIR = Path(r"D:\data\Các bảng mã VNACCS")
METADATA_FILE = OUTPUT_DIR / "metadata.csv"

HEADLESS = True

PAGE_WAIT_MS = 1500
DOWNLOAD_DELAY = 0.3

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".csv",
    ".zip",
    ".rar",
    ".txt",
    ".xml",
}


# ============================================================
# TAB CONFIG
# ============================================================

# Tên hiển thị trên website
TAB_NAMES = [
    "TỔNG HỢP",
    "THUẾ",
    "ĐỊA DANH - ĐỊA ĐIỂM",
]


# ============================================================
# UTILS
# ============================================================


def sanitize_filename(name: str) -> str:
    """
    Làm sạch tên file cho Windows.
    """
    name = unquote(name)

    name = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    name = name.rstrip(". ")

    if not name:
        name = "document"

    return name[:200]


def sanitize_folder_name(name: str) -> str:
    name = sanitize_filename(name)

    replacements = {
        "TỔNG HỢP": "Tổng hợp",
        "THUẾ": "Thuế",
        "ĐỊA DANH - ĐỊA ĐIỂM": "Địa danh - Địa điểm",
    }

    return replacements.get(name.upper(), name)


def is_file_url(url: str) -> bool:
    path = urlparse(url).path.lower()

    return any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def extension_from_content_type(content_type: str) -> str:
    content_type = content_type.lower()

    mapping = {
        "application/pdf": ".pdf",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/csv": ".csv",
        "application/zip": ".zip",
        "application/x-rar-compressed": ".rar",
        "text/plain": ".txt",
        "text/xml": ".xml",
        "application/xml": ".xml",
    }

    for mime, ext in mapping.items():

        if mime in content_type:
            return ext

    return ""


# ============================================================
# HTTP SESSION
# ============================================================


def create_session():
    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131 Safari/537.36"
            ),
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": START_URL,
        }
    )

    return session


# ============================================================
# METADATA
# ============================================================


def load_downloaded_urls():
    urls = set()

    if not METADATA_FILE.exists():
        return urls

    try:

        with open(
            METADATA_FILE,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                url = row.get("download_url")

                if url:
                    urls.add(url)

                final_url = row.get("final_url")

                if final_url:
                    urls.add(final_url)

    except Exception as exc:

        print(f"[WARN] Không đọc được metadata: {exc}")

    return urls


# ============================================================
# FILE NAME
# ============================================================


def get_filename_from_response(
    response: requests.Response,
    fallback_title: str,
):
    disposition = response.headers.get(
        "Content-Disposition",
        "",
    )

    # ----------------------------------------
    # RFC 5987 filename*=UTF-8''
    # ----------------------------------------

    match = re.search(
        r"filename\*=UTF-8''([^;]+)",
        disposition,
        re.I,
    )

    if match:

        return sanitize_filename(match.group(1))

    # ----------------------------------------
    # filename=""
    # ----------------------------------------

    match = re.search(
        r'filename="?([^";]+)',
        disposition,
        re.I,
    )

    if match:

        return sanitize_filename(match.group(1))

    # ----------------------------------------
    # URL
    # ----------------------------------------

    url_filename = Path(urlparse(response.url).path).name

    if url_filename and "." in url_filename:

        return sanitize_filename(url_filename)

    # ----------------------------------------
    # fallback title
    # ----------------------------------------

    extension = extension_from_content_type(
        response.headers.get(
            "Content-Type",
            "",
        )
    )

    if not extension:
        extension = ".bin"

    return sanitize_filename(fallback_title) + extension


# ============================================================
# DOWNLOAD
# ============================================================


def download_file(
    session: requests.Session,
    url: str,
    title: str,
    tab_name: str,
    downloaded_urls: set[str],
    writer,
):

    if url in downloaded_urls:

        print(f"[SKIP URL] {url}")

        return False

    print(f"[DOWNLOAD?] {url}")

    try:

        response = session.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=60,
        )

        response.raise_for_status()

    except Exception as exc:

        print(f"[ERROR] {url}")

        print(f"        {exc}")

        return False

    final_url = response.url

    content_type = response.headers.get(
        "Content-Type",
        "",
    ).lower()

    # ----------------------------------------
    # Không lưu HTML
    # ----------------------------------------

    if "text/html" in content_type:

        response.close()

        print("[SKIP] URL trả về HTML, không phải file.")

        return False

    filename = get_filename_from_response(
        response=response,
        fallback_title=title,
    )

    extension = Path(filename).suffix.lower()

    # ----------------------------------------
    # Nếu không có extension hợp lệ
    # ----------------------------------------

    if extension not in ALLOWED_EXTENSIONS:

        inferred = extension_from_content_type(content_type)

        if inferred:

            filename = Path(filename).stem + inferred

    # ========================================================
    # SUBFOLDER BY TAB
    # ========================================================

    folder_name = sanitize_folder_name(tab_name)

    tab_dir = OUTPUT_DIR / folder_name

    tab_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    filepath = tab_dir / filename

    # ----------------------------------------
    # Nếu file tồn tại
    # ----------------------------------------

    if filepath.exists() and filepath.stat().st_size > 0:

        print(f"[SKIP FILE] {filepath.name}")

        downloaded_urls.add(url)
        downloaded_urls.add(final_url)

        response.close()

        return False

    print(f"[DOWNLOAD] {folder_name} / {filename}")

    try:

        with open(
            filepath,
            "wb",
        ) as f:

            for chunk in response.iter_content(chunk_size=128 * 1024):

                if not chunk:
                    continue

                f.write(chunk)

    except Exception as exc:

        print(f"[WRITE ERROR] {exc}")

        if filepath.exists():
            filepath.unlink()

        response.close()

        return False

    response.close()

    size = filepath.stat().st_size

    print(f"[OK] {filepath.name} " f"({size / 1024 / 1024:.2f} MB)")

    downloaded_urls.add(url)
    downloaded_urls.add(final_url)

    writer.writerow(
        {
            "tab": tab_name,
            "title": title,
            "filename": filename,
            "download_url": url,
            "final_url": final_url,
            "content_type": content_type,
            "size_bytes": size,
        }
    )

    return True


# ============================================================
# EXTRACT ROW TITLE
# ============================================================


def get_row_title(anchor):
    """
    Từ link 'Tải về', tìm tên bảng mã ở cùng dòng <tr>.
    """

    row = anchor.find_parent("tr")

    if not row:
        return "document"

    cells = row.find_all(["td", "th"])

    texts = []

    for cell in cells:

        text = cell.get_text(
            " ",
            strip=True,
        )

        if text:
            texts.append(text)

    # bỏ STT và "Tải về"
    texts = [text for text in texts if text.lower() != "tải về" and not text.isdigit()]

    if texts:
        return texts[0]

    return "document"


# ============================================================
# EXTRACT DOWNLOAD LINKS
# ============================================================


def extract_download_links(
    html: str,
    current_url: str,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    results = []

    seen = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):

        text = a.get_text(
            " ",
            strip=True,
        )

        href = a.get(
            "href",
            "",
        ).strip()

        if not href:
            continue

        # ----------------------------------------
        # chỉ lấy link "Tải về" hoặc file trực tiếp
        # ----------------------------------------

        is_download = (
            "tải về" in text.lower() or "tai ve" in text.lower() or is_file_url(href)
        )

        if not is_download:
            continue

        full_url = urljoin(
            current_url,
            href,
        )

        if full_url in seen:
            continue

        seen.add(full_url)

        title = get_row_title(a)

        results.append(
            {
                "title": title,
                "url": full_url,
            }
        )

    return results


# ============================================================
# FIND TAB
# ============================================================


def find_tab(page, tab_name: str):
    """
    Tìm tab theo text.
    Hỗ trợ cả <a>, <li>, <button>.
    """

    # Exact text trước
    locator = page.get_by_text(
        tab_name,
        exact=True,
    )

    if locator.count() > 0:
        return locator.first

    # fallback
    locator = page.locator(f"text={tab_name}")

    if locator.count() > 0:
        return locator.first

    return None


# ============================================================
# PROCESS TAB
# ============================================================


def process_tab(
    page,
    session,
    tab_name,
    downloaded_urls,
    writer,
    csv_file,
):

    print()
    print("=" * 80)

    print(f"TAB: {tab_name}")

    print("=" * 80)

    tab = find_tab(
        page,
        tab_name,
    )

    if tab is None:

        print(f"[ERROR] Không tìm thấy tab: {tab_name}")

        return 0

    # ========================================================
    # CLICK TAB
    # ========================================================

    try:

        tab.click()

    except Exception:

        try:

            tab.click(force=True)

        except Exception as exc:

            print(f"[ERROR] Không click được tab {tab_name}: {exc}")

            return 0

    page.wait_for_timeout(PAGE_WAIT_MS)

    # ========================================================
    # HTML AFTER CLICK
    # ========================================================

    html = page.content()

    current_url = page.url

    links = extract_download_links(
        html,
        current_url,
    )

    print(f"Found: {len(links)} download links")

    count = 0

    for index, item in enumerate(
        links,
        start=1,
    ):

        print()

        print(f"[{index}/{len(links)}] " f"{item['title']}")

        success = download_file(
            session=session,
            url=item["url"],
            title=item["title"],
            tab_name=tab_name,
            downloaded_urls=downloaded_urls,
            writer=writer,
        )

        if success:

            count += 1

            csv_file.flush()

        time.sleep(DOWNLOAD_DELAY)

    return count


# ============================================================
# MAIN
# ============================================================


def crawl():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = create_session()

    downloaded_urls = load_downloaded_urls()

    metadata_exists = METADATA_FILE.exists()

    total_downloaded = 0

    # ========================================================
    # METADATA
    # ========================================================

    with open(
        METADATA_FILE,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:

        fieldnames = [
            "tab",
            "title",
            "filename",
            "download_url",
            "final_url",
            "content_type",
            "size_bytes",
        ]

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        if not metadata_exists:

            writer.writeheader()

            csv_file.flush()

        # ====================================================
        # PLAYWRIGHT
        # ====================================================

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=HEADLESS,
            )

            context = browser.new_context(
                locale="vi-VN",
                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131 Safari/537.36"
                ),
            )

            page = context.new_page()

            print("=" * 80)

            print("VNACCS / VCIS CODE TABLE CRAWLER")

            print("=" * 80)

            print(f"URL: {START_URL}")

            print(f"Output: {OUTPUT_DIR}")

            # =================================================
            # OPEN PAGE
            # =================================================

            page.goto(
                START_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            page.wait_for_timeout(2000)

            # =================================================
            # PROCESS ALL 3 TABS
            # =================================================

            for tab_name in TAB_NAMES:

                count = process_tab(
                    page=page,
                    session=session,
                    tab_name=tab_name,
                    downloaded_urls=downloaded_urls,
                    writer=writer,
                    csv_file=csv_file,
                )

                total_downloaded += count

            browser.close()

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 80)

    print("FINISHED")

    print("=" * 80)

    print(f"New files downloaded: " f"{total_downloaded}")

    print(f"Output folder:")

    print(OUTPUT_DIR)

    print(f"Metadata:")

    print(METADATA_FILE)


if __name__ == "__main__":
    crawl()
