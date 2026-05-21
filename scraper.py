# =====================================================
# SCRAPER MODULE
# =====================================================
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

        url = url.strip()

        if not url.startswith("http"):
            url = "https://" + url

        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()

        return response.text

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

    # remove non-content elements
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)

    # normalize whitespace aggressively
    return " ".join(text.split())


# =====================================================
# SCRAPE SINGLE PAGE
# =====================================================
def scrape_single(url: str) -> str:
    return clean_html(fetch_page(url))


# =====================================================
# MAIN PIPELINE FUNCTION
# =====================================================
def get_landing_context(
    campaign_type: str,
    landing_page: Optional[str],
    landing_pages: Optional[List[str]]
) -> str:

    texts: List[str] = []

    # -------------------------------------------------
    # SINGLE PAGE CAMPAIGNS
    # -------------------------------------------------
    if campaign_type != "PMax":
        if landing_page:
            content = scrape_single(landing_page)
            if content:
                texts.append(content)

    # -------------------------------------------------
    # PMax MULTI PAGE CAMPAIGNS
    # -------------------------------------------------
    else:
        if landing_pages:
            for url in landing_pages:
                content = scrape_single(url)
                if content:
                    texts.append(content)

    # ALWAYS return string (never None)
    return "\n\n".join(texts).strip()
