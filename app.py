# =====================================================
# UNIFIED NEGATIVE KEYWORDER
# Combines:
# - App 1 semantic intelligence
# - App 2 infrastructure + caching
# =====================================================

import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import json
import math
import re
import sqlite3
import time
import requests

from bs4 import BeautifulSoup
from datetime import datetime

# =====================================================
# CONFIG
# =====================================================

st.set_page_config(
    page_title="Unified Negative Keyworder",
    layout="wide"
)

st.title("Unified Negative Keyworder")

# =====================================================
# GEMINI
# =====================================================

genai.configure(
    api_key=st.secrets["GEMINI_API_KEY"]
)

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

# =====================================================
# SQLITE CACHE
# =====================================================

conn = sqlite3.connect(
    "negative_keyword_cache.db",
    check_same_thread=False
)

cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS brand_cache (
    hash TEXT PRIMARY KEY,
    data TEXT,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS classification_cache (
    hash TEXT PRIMARY KEY,
    data TEXT,
    created_at TEXT
)
""")

conn.commit()

# =====================================================
# SESSION STATE
# =====================================================

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if "running" not in st.session_state:
    st.session_state.running = False

# =====================================================
# HELPERS
# =====================================================

def normalize(t):

    return re.sub(
        r"\s+",
        " ",
        str(t).strip().lower()
    )


def hash_text(text):

    return hashlib.md5(
        text.encode()
    ).hexdigest()


def chunk_list(lst, size=75):

    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def safe_generate(prompt):

    try:

        r = model.generate_content(prompt)

        return {
            "ok": True,
            "text": r.text.strip().replace("```", "")
        }

    except Exception as e:

        return {
            "ok": False,
            "error": str(e)
        }


def extract_json(text):

    try:
        return json.loads(text)

    except:

        match = re.search(
            r"\{.*\}",
            text,
            re.DOTALL
        )

        if match:

            try:
                return json.loads(match.group())

            except:
                return None

    return None

# =====================================================
# CACHE HELPERS
# =====================================================

def get_cached_brand(hash_key):

    cur.execute(
        "SELECT data FROM brand_cache WHERE hash=?",
        (hash_key,)
    )

    row = cur.fetchone()

    if row:
        return json.loads(row[0])

    return None


def save_cached_brand(hash_key, data):

    cur.execute(
        """
        INSERT OR REPLACE INTO brand_cache
        VALUES (?, ?, ?)
        """,
        (
            hash_key,
            json.dumps(data),
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()


def get_cached_classification(hash_key):

    cur.execute(
        "SELECT data FROM classification_cache WHERE hash=?",
        (hash_key,)
    )

    row = cur.fetchone()

    if row:
        return json.loads(row[0])

    return None


def save_cached_classification(hash_key, data):

    cur.execute(
        """
        INSERT OR REPLACE INTO classification_cache
        VALUES (?, ?, ?)
        """,
        (
            hash_key,
            json.dumps(data),
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()

# =====================================================
# SCRAPER
# =====================================================

def scrape_page(url):

    try:

        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=10
        )

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        for t in soup([
            "script",
            "style",
            "footer",
            "nav",
            "svg"
        ]):
            t.extract()

        text = " ".join([

            soup.title.get_text(
                " ",
                strip=True
            ) if soup.title else "",

            " ".join(
                p.get_text(
                    " ",
                    strip=True
                )
                for p in soup.find_all("p")
            )
        ])

        return re.sub(
            r"\s+",
            " ",
            text
        )[:6000]

    except:
        return ""


def scrape_multiple_pages(urls):

    combined = []

    for url in urls:

        page = scrape_page(url)

        if page:
            combined.append(page)

    return "\n".join(combined)[:12000]

# =====================================================
# BRAND MODEL
# =====================================================

def build_brand_model(
    page_text,
    target_keywords,
    campaign_type
):

    brand_hash = hash_text(
        page_text +
        target_keywords +
        campaign_type
    )

    cached = get_cached_brand(brand_hash)

    if cached:
        return cached

    prompt = f"""
Return ONLY valid JSON.

FORMAT:
{{
  "business_type": "",
  "summary": "",
  "core_offerings": [],
  "safe_roots": [],
  "commercial_intents": [],
  "low_value_intents": []
}}

You are building a PPC commercial relevance model.

RULES:
- identify valuable commercial intent
- identify low commercial intent
- identify protected commercial roots
- do not invent products/services
- do not over-generalize

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

PAGE:
{page_text[:5000]}
"""

    result = safe_generate(prompt)

    if not result["ok"]:

        return {
            "business_type": "unknown",
            "summary": "unknown",
            "core_offerings": [],
            "safe_roots": [],
            "commercial_intents": [],
            "low_value_intents": []
        }

    data = extract_json(result["text"])

    if not data:

        data = {
            "business_type": "unknown",
            "summary": "unknown",
            "core_offerings": [],
            "safe_roots": [],
            "commercial_intents": [],
            "low_value_intents": []
        }

    save_cached_brand(
        brand_hash,
        data
    )

    return data

# =====================================================
# CONTEXTUAL PREFILTER
# =====================================================

def contextual_prefilter(
    terms,
    brand
):

    auto_negative = []
    remaining = []

    low_value_intents = set([
        normalize(x)
        for x in brand.get(
            "low_value_intents",
            []
        )
    ])

    for term in terms:

        matched = False

        for trigger in low_value_intents:

            if trigger in term:

                auto_negative.append(term)
                matched = True
                break

        if not matched:
            remaining.append(term)

    return auto_negative, remaining

# =====================================================
# AI CLASSIFICATION
# =====================================================

def classify_terms_batch(
    batch_terms,
    brand,
    target_keywords,
    campaign_type
):

    cache_key = hash_text(
        json.dumps(batch_terms) +
        json.dumps(brand) +
        target_keywords +
        campaign_type
    )

    cached = get_cached_classification(cache_key)

    if cached:
        return cached

    formatted_terms = "\n".join(
        [f"- {t}" for t in batch_terms]
    )

    prompt = f"""
You are a senior PPC strategist.

Return ONLY valid JSON.

FORMAT:
{{
  "negative": [],
  "review": [],
  "positive": []
}}

RULES:
- protect commercial intent
- protect core offerings
- protect safe roots
- do not invent concepts
- do not over-generalize
- classify conservatively

NEGATIVE:
irrelevant or low-value traffic

REVIEW:
ambiguous traffic

POSITIVE:
commercially relevant traffic

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

BRAND MODEL:
{json.dumps(brand)}

SEARCH TERMS:
{formatted_terms}
"""

    result = safe_generate(prompt)

    if not result["ok"]:

        return {
            "negative": [],
            "review": [],
            "positive": []
        }

    data = extract_json(result["text"])

    if (
        not data
        or "negative" not in data
        or "review" not in data
        or "positive" not in data
    ):

        data = {
            "negative": [],
            "review": [],
            "positive": []
        }

    save_cached_classification(
        cache_key,
        data
    )

    return data

# =====================================================
# SAFE ROOT ENGINE
# =====================================================

def build_root_negatives(
    negatives,
    protected_roots
):

    approved_roots = {
        "jobs",
        "job",
        "career",
        "careers",
        "salary",
        "training",
        "tutorial",
        "guide",
        "free",
        "reddit",
        "youtube",
        "pdf"
    }

    roots = []

    for term in negatives:

        for word in term.split():

            word = normalize(word)

            if word in protected_roots:
                continue

            if word in approved_roots:
                roots.append(word)

    return sorted(set(roots))

# =====================================================
# SAFE VARIATION ENGINE
# =====================================================

def expand_variations(roots):

    expanded = set()

    for r in roots:

        expanded.add(r)

        if not r.endswith("s"):
            expanded.add(f"{r}s")

    return sorted(expanded)

# =====================================================
# GOOGLE ADS FORMAT
# =====================================================

def format_google_ads(terms):

    out = []

    for t in terms:

        t = t.strip()

        if not t:
            continue

        if " " in t:
            out.append(f'"{t}"')

        else:
            out.append(t)

    return sorted(set(out))

# =====================================================
# INPUTS
# =====================================================

campaign_type = st.selectbox(
    "Campaign Type",
    [
        "Select",
        "Search",
        "Shopping",
        "PMax",
        "Display"
    ]
)

landing_pages = ""

if campaign_type == "PMax":

    landing_pages = st.text_area(
        "Landing Page URLs (One Per Line)",
        height=140
    )

else:

    landing_pages = st.text_input(
        "Landing Page URL"
    )

target_keywords = st.text_area(
    "Target Keywords",
    height=120
)

uploaded_file = st.file_uploader(
    "Search Terms CSV",
    type=["csv"]
)

if uploaded_file:

    df = pd.read_csv(
        uploaded_file,
        engine="python"
    )

    col = st.selectbox(
        "Search Terms Column",
        df.columns
    )

    st.session_state.search_terms = "\n".join(
        df[col]
        .dropna()
        .astype(str)
    )

# =====================================================
# VALIDATION
# =====================================================

def validate():

    if campaign_type == "Select":
        return "Select campaign type"

    if not landing_pages:
        return "Missing landing page"

    if uploaded_file is None:
        return "Missing CSV"

    if not st.session_state.search_terms.strip():
        return "Missing search terms"

    return None

# =====================================================
# RUN
# =====================================================

if st.button("Analyse"):

    validation_error = validate()

    if validation_error:
        st.error(validation_error)
        st.stop()

    # =====================================================
    # NORMALIZE + DEDUPE
    # =====================================================

    terms = sorted(set([

        normalize(t)

        for t in st.session_state.search_terms.split("\n")

        if t.strip()

    ]))

    # =====================================================
    # SCRAPE
    # =====================================================

    with st.spinner("Scraping landing pages..."):

        if campaign_type == "PMax":

            urls = [
                u.strip()
                for u in landing_pages.split("\n")
                if u.strip()
            ]

            page_text = scrape_multiple_pages(urls)

        else:

            page_text = scrape_page(landing_pages)

    # =====================================================
    # BRAND MODEL
    # =====================================================

    with st.spinner("Building brand model..."):

        brand = build_brand_model(
            page_text,
            target_keywords,
            campaign_type
        )

    # =====================================================
    # PROTECTED ROOTS
    # =====================================================

    protected_roots = set()

    for w in target_keywords.split():
        protected_roots.add(normalize(w))

    for w in brand.get("safe_roots", []):
        protected_roots.add(normalize(w))

    # =====================================================
    # CONTEXTUAL PREFILTER
    # =====================================================

    auto_negative, remaining_terms = contextual_prefilter(
        terms,
        brand
    )

    st.info(f"""
Processed:
- {len(terms)} total terms
- {len(auto_negative)} auto negatives
- {len(remaining_terms)} terms requiring AI classification
""")

    # =====================================================
    # AI CLASSIFICATION
    # =====================================================

    search_term_negatives = []
    review_terms = []
    positive_terms = []

    batches = list(
        chunk_list(
            remaining_terms,
            75
        )
    )

    progress = st.progress(0)
    status = st.empty()

    for i, batch in enumerate(batches):

        progress.progress(
            int(((i + 1) / len(batches)) * 100)
        )

        status.info(
            f"Processing batch {i+1}/{len(batches)}"
        )

        result = classify_terms_batch(
            batch,
            brand,
            target_keywords,
            campaign_type
        )

        search_term_negatives.extend(
            result.get("negative", [])
        )

        review_terms.extend(
            result.get("review", [])
        )

        positive_terms.extend(
            result.get("positive", [])
        )

        time.sleep(0.5)

    # =====================================================
    # MERGE AUTO NEGATIVES
    # =====================================================

    search_term_negatives.extend(
        auto_negative
    )

    # =====================================================
    # ROOT NEGATIVES
    # =====================================================

    root_negatives = build_root_negatives(
        search_term_negatives,
        protected_roots
    )

    # =====================================================
    # VARIATIONS
    # =====================================================

    variations = expand_variations(
        root_negatives
    )

    # =====================================================
    # FINAL LIST
    # =====================================================

    final_raw = (
        search_term_negatives +
        root_negatives +
        variations
    )

    final = format_google_ads(
        final_raw
    )

    # =====================================================
    # OUTPUT
    # =====================================================

    st.success("Analysis Complete")

    st.subheader("Brand Model")
    st.json(brand)

    st.subheader("Review Queue")

    st.write(
        sorted(set(review_terms))
        if review_terms
        else "No review terms"
    )

    st.subheader("Positive Terms")

    st.write(
        sorted(set(positive_terms))
        if positive_terms
        else "No positives"
    )

    st.subheader("Search-Term Negatives")

    st.write(
        sorted(set(search_term_negatives))
    )

    st.subheader("Root Negatives")

    st.write(root_negatives)

    st.subheader("Variations")

    st.write(variations)

    st.subheader("Final Google Ads Negative List")

    st.text_area(
        "Copy & Paste",
        "\n".join(final),
        height=500
    )

    st.download_button(
        "Download TXT",
        "\n".join(final),
        file_name="negative_keywords.txt"
    )
