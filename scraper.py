import requests
from bs4 import BeautifulSoup
from typing import List, Optional


# =====================================================
# CONFIG
# =====================================================
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

TIMEOUT = 10


# =====================================================
# FETCH PAGE
# =====================================================
def fetch_page(url: str) -> str:
    try:
        if not url:
            return ""

        if not url.startswith("http"):
            url = "https://" + url

        res = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        res.raise_for_status()
        return res.text

    except Exception as e:
        print(f"[SCRAPER ERROR] {url} -> {e}")
        return ""


# =====================================================
# CLEAN HTML
# =====================================================
def clean_html(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # remove noise elements
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav", "header"]):
        tag.decompose()

    # extract readable text
    text = soup.get_text(separator=" ", strip=True)

    # normalize whitespace
    text = " ".join(text.split())

    return text.strip()


# =====================================================
# SCRAPE SINGLE PAGE
# =====================================================
def scrape_single(url: str) -> str:
    html = fetch_page(url)
    return clean_html(html)


# =====================================================
# MAIN PIPELINE FUNCTION
# =====================================================
def get_landing_context(
    campaign_type: str,
    landing_page: Optional[str],
    landing_pages: Optional[List[str]]
) -> str:

    all_text = []

    # -------------------------
    # SINGLE PAGE CAMPAIGNS
    # -------------------------
    if campaign_type != "PMax":
        if landing_page:
            scraped = scrape_single(landing_page)
            if scraped:
                all_text.append(scraped)

    # -------------------------
    # PMax MULTI PAGE CAMPAIGNS
    # -------------------------
    else:
        if landing_pages:
            for url in landing_pages:
                scraped = scrape_single(url)
                if scraped:
                    all_text.append(scraped)

    # merge safely
    combined = "\n\n".join(all_text).strip()

    return combined
