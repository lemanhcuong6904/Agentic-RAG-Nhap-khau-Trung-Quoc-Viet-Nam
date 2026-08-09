from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from tqdm import tqdm

# ============================================================
# CONFIG
# ============================================================

START_URL = (
    "https://www.customs.gov.vn/index.jsp"
    "?category=General+indicators"
    "&group=Statistical+data"
    "&pageId=5002"
)

OUTPUT_DIR = Path(r"D:\data\Customs statistics")
METADATA_FILE = OUTPUT_DIR / "metadata.csv"

START_YEAR = 2026
END_YEAR = 2020

HEADLESS = True

PAGE_DELAY = 1.0
DOWNLOAD_DELAY = 0.3

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".csv",
    ".zip",
}


# ============================================================
# UTILITY
# ============================================================


def sanitize_filename(name: str) -> str:
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

    return name[:200]


def get_extension_from_content_type(content_type: str) -> str:
    content_type = content_type.lower()

    mapping = {
        "application/pdf": ".pdf",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/csv": ".csv",
        "application/zip": ".zip",
    }

    for key, value in mapping.items():
        if key in content_type:
            return value

    return ""


def is_document_url(url: str) -> bool:
    path = urlparse(url).path.lower()

    return any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def extract_year_from_url(url: str):
    """
    Ví dụ:
    https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2026/8/6/a.pdf

    -> 2026
    """

    match = re.search(
        r"/(20\d{2})/",
        url,
    )

    if match:
        return int(match.group(1))

    # fallback: tìm năm trong filename
    filename = Path(urlparse(url).path).name

    match = re.search(
        r"\b(20\d{2})\b",
        filename,
    )

    if match:
        return int(match.group(1))

    return None


def year_allowed(url: str) -> bool:
    year = extract_year_from_url(url)

    if year is None:
        return True

    return END_YEAR <= year <= START_YEAR


# ============================================================
# REQUESTS SESSION
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

    except Exception as exc:
        print(
            "[WARN] Không đọc được metadata:",
            exc,
        )

    return urls


# ============================================================
# DOWNLOAD
# ============================================================


def get_filename(response, url):
    disposition = response.headers.get(
        "Content-Disposition",
        "",
    )

    # filename*=UTF-8''
    match = re.search(
        r"filename\*=UTF-8''([^;]+)",
        disposition,
        re.I,
    )

    if match:
        return sanitize_filename(match.group(1))

    # filename=
    match = re.search(
        r'filename="?([^";]+)',
        disposition,
        re.I,
    )

    if match:
        return sanitize_filename(match.group(1))

    filename = Path(urlparse(response.url).path).name

    filename = sanitize_filename(filename)

    if "." not in filename:

        extension = get_extension_from_content_type(
            response.headers.get(
                "Content-Type",
                "",
            )
        )

        filename += extension

    return filename


def download_file(
    session,
    url,
    source_page,
    downloaded_urls,
    writer,
):
    if url in downloaded_urls:
        return False

    if not year_allowed(url):
        return False

    try:

        response = session.get(
            url,
            stream=True,
            timeout=60,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:

        print(f"[ERROR] {url}\n" f"        {exc}")

        return False

    content_type = response.headers.get(
        "Content-Type",
        "",
    ).lower()

    final_url = response.url

    # tránh lưu HTML
    if "text/html" in content_type:

        response.close()

        return False

    filename = get_filename(
        response,
        final_url,
    )

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:

        inferred = get_extension_from_content_type(content_type)

        if not inferred:

            response.close()

            return False

        filename += inferred

    filepath = OUTPUT_DIR / filename

    # ----------------------------------------
    # File đã có
    # ----------------------------------------

    if filepath.exists() and filepath.stat().st_size > 0:

        print(f"[SKIP] {filename}")

        downloaded_urls.add(url)

        response.close()

        return False

    # ----------------------------------------
    # Download
    # ----------------------------------------

    total_size = int(
        response.headers.get(
            "Content-Length",
            0,
        )
        or 0
    )

    print(f"[DOWNLOAD] {filename}")

    try:

        with open(
            filepath,
            "wb",
        ) as f:

            with tqdm(
                total=total_size,
                unit="B",
                unit_scale=True,
                leave=False,
                desc=filename[:50],
            ) as bar:

                for chunk in response.iter_content(chunk_size=128 * 1024):

                    if not chunk:
                        continue

                    f.write(chunk)

                    bar.update(len(chunk))

    except Exception as exc:

        print(
            "[ERROR WRITE]",
            exc,
        )

        if filepath.exists():
            filepath.unlink()

        response.close()

        return False

    response.close()

    size = filepath.stat().st_size

    year = extract_year_from_url(url)

    writer.writerow(
        {
            "year": year,
            "filename": filename,
            "source_page": source_page,
            "download_url": url,
            "size_bytes": size,
        }
    )

    downloaded_urls.add(url)

    print(f"[OK] {filename} " f"({size / 1024 / 1024:.2f} MB)")

    return True


# ============================================================
# EXTRACT DOCUMENT LINKS
# ============================================================


def extract_document_links(
    html,
    current_url,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    urls = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):

        href = a.get(
            "href",
            "",
        ).strip()

        if not href:
            continue

        full_url = urljoin(
            current_url,
            href,
        )

        if is_document_url(full_url):

            urls.add(full_url)

    return sorted(urls)


# ============================================================
# EXTRACT YEARS DISPLAYED ON PAGE
# ============================================================


def extract_page_years(text):
    """
    Tìm các năm xuất hiện trong bảng.

    Ví dụ:
        05-2026
        04/2026
        2026
    """

    years = re.findall(
        r"\b(20\d{2})\b",
        text,
    )

    return [int(y) for y in years]


# ============================================================
# FIND PAGINATION SELECT
# ============================================================


def find_page_select(page):
    """
    Website có:
        Trang: [2 ▼]

    Ta tìm select có nhiều option số.
    """

    selects = page.locator("select")

    count = selects.count()

    for i in range(count):

        select = selects.nth(i)

        try:

            options = select.locator("option")

            option_count = options.count()

            if option_count < 2:
                continue

            values = []

            for j in range(
                min(
                    option_count,
                    20,
                )
            ):

                text = options.nth(j).inner_text().strip()

                if text.isdigit():

                    values.append(int(text))

            # page dropdown sẽ có nhiều số
            if len(values) >= 2:

                return select

        except Exception:
            continue

    return None


# ============================================================
# MAIN CRAWLER
# ============================================================


def crawl():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    session = create_session()

    downloaded_urls = load_downloaded_urls()

    metadata_exists = METADATA_FILE.exists()

    downloaded_count = 0

    with open(
        METADATA_FILE,
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:

        fieldnames = [
            "year",
            "filename",
            "source_page",
            "download_url",
            "size_bytes",
        ]

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        if not metadata_exists:

            writer.writeheader()

            csv_file.flush()

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=HEADLESS,
            )

            context = browser.new_context(
                locale="vi-VN",
            )

            page = context.new_page()

            # =================================================
            # LOAD FIRST PAGE
            # =================================================

            print("=" * 70)

            print("CUSTOMS STATISTICS CRAWLER")

            print(f"Years: {START_YEAR} -> {END_YEAR}")

            print("=" * 70)

            page.goto(
                START_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            page.wait_for_timeout(2000)

            # =================================================
            # FIND PAGINATION
            # =================================================

            pagination_select = find_page_select(page)

            if pagination_select is None:

                print("[ERROR] Không tìm thấy " "dropdown phân trang.")

                browser.close()

                return

            options = pagination_select.locator("option")

            total_pages = options.count()

            print(f"Total pages detected: " f"{total_pages}")

            print()

            # =================================================
            # LOOP ALL PAGES
            # =================================================

            for index in range(total_pages):

                # dropdown có thể bị refresh
                # nên phải tìm lại mỗi vòng
                pagination_select = find_page_select(page)

                if pagination_select is None:

                    print("[WARN] Không tìm thấy " "pagination.")

                    break

                options = pagination_select.locator("option")

                if index >= options.count():
                    break

                option = options.nth(index)

                option_text = option.inner_text().strip()

                option_value = option.get_attribute("value")

                print()
                print("=" * 70)

                print(f"PAGE " f"{option_text}/" f"{total_pages}")

                print("=" * 70)

                # --------------------------------------------
                # Change page
                # --------------------------------------------

                if index > 0:

                    old_html = page.content()

                    try:

                        if option_value:

                            pagination_select.select_option(value=option_value)

                        else:

                            pagination_select.select_option(label=option_text)

                    except Exception:

                        pagination_select.select_option(index=index)

                    # chờ AJAX / reload
                    page.wait_for_timeout(1800)

                current_url = page.url

                html = page.content()

                page_text = page.locator("body").inner_text()

                # --------------------------------------------
                # Check year
                # --------------------------------------------

                years = extract_page_years(page_text)

                relevant_years = [y for y in years if END_YEAR <= y <= START_YEAR]

                if years:

                    print(
                        "Years found:",
                        sorted(
                            set(years),
                            reverse=True,
                        )[:10],
                    )

                # Nếu trang hoàn toàn xuống dưới 2020
                # thì dừng luôn.
                if years and max(years) < END_YEAR:

                    print()
                    print(f"Đã xuống dưới " f"năm {END_YEAR}.")

                    print("STOP.")

                    break

                # --------------------------------------------
                # Extract documents
                # --------------------------------------------

                document_urls = extract_document_links(
                    html,
                    current_url,
                )

                document_urls = [url for url in document_urls if year_allowed(url)]

                print(f"Documents found: " f"{len(document_urls)}")

                # --------------------------------------------
                # Download
                # --------------------------------------------

                for url in document_urls:

                    downloaded = download_file(
                        session=session,
                        url=url,
                        source_page=current_url,
                        downloaded_urls=downloaded_urls,
                        writer=writer,
                    )

                    if downloaded:

                        downloaded_count += 1

                        csv_file.flush()

                    time.sleep(DOWNLOAD_DELAY)

                time.sleep(PAGE_DELAY)

            browser.close()

    print()
    print("=" * 70)

    print("FINISHED")

    print("=" * 70)

    print(f"Downloaded new files: " f"{downloaded_count}")

    print(f"Output folder: " f"{OUTPUT_DIR}")

    print(f"Metadata: " f"{METADATA_FILE}")


if __name__ == "__main__":
    crawl()
