import requests
from bs4 import BeautifulSoup
import re

# =========================
# SINGLE PAGE
# =========================

def scrape_page(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        for t in soup(["script", "style", "nav", "footer", "svg"]):
            t.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else ""

        text = " ".join([
            title,
            " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        ])

        return re.sub(r"\s+", " ", text).strip()[:6000]

    except:
        return ""

# =========================
# MULTI PAGE (PMax)
# =========================

def scrape_multiple_pages(urls):
    out = []

    for u in urls:
        t = scrape_page(u)
        if t:
            out.append(t)

    return " ".join(out)[:12000]

# =========================
# ROUTER
# =========================

def get_landing_context(campaign_type, landing_page, landing_pages):

    if campaign_type == "PMax":
        urls = [u.strip() for u in landing_pages.split("\n") if u.strip()]
        return scrape_multiple_pages(urls)

    return scrape_page(landing_page)
