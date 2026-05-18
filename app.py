import streamlit as st
import google.generativeai as genai
import pandas as pd
import re
import json
import math
import requests
from bs4 import BeautifulSoup

# -------------------------
# CONFIG
# -------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

st.set_page_config(
    page_title="Negative Keyworder V2",
    layout="wide"
)

st.title("Negative Keyworder V2")

# -------------------------
# STATE
# -------------------------
if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if "error_message" not in st.session_state:
    st.session_state.error_message = ""

# -------------------------
# HELPERS
# -------------------------
def normalize(t):

    return re.sub(
        r"\s+",
        " ",
        str(t).strip().lower()
    )


def safe_generate(prompt):

    try:

        r = model.generate_content(prompt)

        return {
            "ok": True,
            "text": r.text.strip().replace("```", "")
        }

    except Exception:

        return {
            "ok": False,
            "error": "quota"
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


# -------------------------
# SCRAPE PAGE
# -------------------------
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


# -------------------------
# MULTI PAGE SUPPORT
# -------------------------
def scrape_multiple_pages(urls):

    combined = []

    for url in urls:

        page = scrape_page(url)

        if page:
            combined.append(page)

    return "\n".join(combined)[:12000]


# -------------------------
# BRAND MODEL
# -------------------------
def brand_model(
    page_text,
    target_keywords,
    campaign_type
):

    prompt = f"""
Return ONLY valid JSON.

FORMAT:
{{
  "summary": "",
  "positioning": "",
  "core_offerings": [],
  "safe_roots": []
}}

Extract:
- business summary
- positioning
- core offerings
- safe roots

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

PAGE:
{page_text[:5000]}
"""

    result = safe_generate(prompt)

    if not result["ok"]:
        return None, "quota"

    data = extract_json(
        result["text"]
    )

    if not data:

        return {
            "summary": "unknown",
            "positioning": "mixed",
            "core_offerings": [],
            "safe_roots": []
        }, None

    return data, None


# -------------------------
# BATCH CLASSIFICATION
# -------------------------
def classify_terms_batch(
    batch_terms,
    brand_context,
    target_keywords,
    campaign_type
):

    formatted_terms = "\n".join(
        [f"- {t}" for t in batch_terms]
    )

    # ✅ PATCH: now includes POSITIVE
    prompt = f"""
You are a senior PPC analyst.

Return ONLY valid JSON.

FORMAT:
{{
  "negative": [],
  "review": [],
  "positive": []
}}

RULES:
- NEGATIVE = irrelevant traffic
- REVIEW = uncertain traffic
- POSITIVE = clearly relevant commercial intent (DO NOT include in negatives)
- protect commercial intent
- protect core offerings
- default toward NEGATIVE when unsure

CAMPAIGN:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

BRAND:
{brand_context}

SEARCH TERMS:
{formatted_terms}
"""

    result = safe_generate(prompt)

    if not result["ok"]:
        return None, "quota"

    data = extract_json(
        result["text"]
    )

    # -------------------------
    # STRICT JSON VALIDATION (PATCHED)
    # -------------------------
    if (
        not data
        or "negative" not in data
        or "review" not in data
        or "positive" not in data   # ✅ PATCH
    ):

        return {
            "negative": [],
            "review": [],
            "positive": []   # ✅ PATCH
        }, None

    return data, None


# -------------------------
# ROOT EXTRACTION
# -------------------------
def extract_roots(
    term,
    protected_roots
):

    roots = []

    for w in term.split():

        w = w.lower()

        if w in protected_roots:
            continue

        if len(w) <= 2:
            continue

        roots.append(w)

    return roots


# -------------------------
# REMOVE DUPLICATE ROOTS
# -------------------------
def dedupe_roots(roots):

    cleaned = []

    seen = set()

    for r in roots:

        r = normalize(r)

        if r in seen:
            continue

        seen.add(r)

        cleaned.append(r)

    return cleaned


# -------------------------
# VARIATIONS
# -------------------------
def expand_variations(negatives):

    sample = negatives[:100]

    prompt = f"""
Expand ONLY plural or semantic variants.

RULES:
- NO invention
- NO unrelated ideas
- ONLY close variants
- one per line

NEGATIVES:
{sample}
"""

    result = safe_generate(prompt)

    if not result["ok"]:
        return []

    return [

        w.strip().lower()

        for w in result["text"].split("\n")

        if w.strip()

    ][:50]


# -------------------------
# GOOGLE ADS FORMAT
# -------------------------
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


# -------------------------
# INPUTS
# -------------------------
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
        height=140,
        help="Optional multi-page analysis for PMax."
    )

else:

    landing_pages = st.text_input(
        "Landing Page URL"
    )

target_keywords = ""

if campaign_type == "Search":

    target_keywords = st.text_area(
        "Target Keywords",
        height=120
    )

elif campaign_type == "Shopping":

    target_keywords = st.text_area(
        "Optional Product Keywords",
        height=100
    )

elif campaign_type == "PMax":

    st.info(
        "PMax relies primarily on landing page and behavioural context."
    )

elif campaign_type == "Display":

    st.info(
        "Display campaigns rely heavily on contextual relevance."
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


# -------------------------
# VALIDATION (UNCHANGED LOGIC)
# -------------------------
def validate():

    if campaign_type == "Select":
        return "Select campaign type"

    if not landing_pages:
        return "Missing landing page"

    if uploaded_file is None:
        return "Missing CSV"

    if not st.session_state.search_terms.strip():
        return "Missing search terms"

    if (
        campaign_type == "Search"
        and not target_keywords.strip()
    ):
        return "Missing target keywords"

    return None


if st.session_state.error_message:
    st.error(st.session_state.error_message)


# -------------------------
# RUN PIPELINE
# -------------------------
if st.button("Analyse"):

    st.session_state.error_message = ""

    validation_error = validate()

    if validation_error:
        st.session_state.error_message = validation_error
        st.stop()

    with st.spinner("Scraping landing page..."):
        if campaign_type == "PMax":
            urls = [u.strip() for u in landing_pages.split("\n") if u.strip()]
            page_text = scrape_multiple_pages(urls)
        else:
            page_text = scrape_page(landing_pages)

    with st.spinner("Building brand model..."):
        brand, err = brand_model(page_text, target_keywords, campaign_type)

        if err:
            st.session_state.error_message = "⚠️ Daily Gemini quota reached. Please try again later."
            st.stop()

    protected_roots = set()

    for w in target_keywords.split():
        protected_roots.add(normalize(w))

    for w in brand.get("safe_roots", []):
        protected_roots.add(normalize(w))

    terms = sorted(set([
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]))

    search_term_negatives = []
    review_terms = []
    positive_terms = []   # ✅ PATCH

    progress = st.progress(0)
    status = st.empty()

    BATCH_SIZE = 75
    total_batches = math.ceil(len(terms) / BATCH_SIZE)

    for batch_num, start in enumerate(range(0, len(terms), BATCH_SIZE)):

        end = start + BATCH_SIZE
        batch = terms[start:end]

        progress.progress(int(((batch_num + 1) / total_batches) * 100))
        status.info(f"Processing batch {batch_num+1}/{total_batches}")

        result, err = classify_terms_batch(
            batch,
            brand,
            target_keywords,
            campaign_type
        )

        if err:
            st.session_state.error_message = "⚠️ Daily Gemini quota reached. Please try again later."
            st.stop()

        search_term_negatives.extend(result.get("negative", []))
        review_terms.extend(result.get("review", []))
        positive_terms.extend(result.get("positive", []))  # ✅ PATCH

    ai_roots = []

    for t in search_term_negatives:
        ai_roots.extend(extract_roots(t, protected_roots))

    ai_roots = dedupe_roots(ai_roots)

    ai_variations = expand_variations(search_term_negatives)

    final_raw = search_term_negatives + ai_roots + ai_variations
    final = format_google_ads(final_raw)

    st.success("Analysis Complete")

    st.subheader("Brand Positioning Summary")
    st.json(brand)

    st.subheader("Review Queue (Manual Audit Required)")
    st.write(sorted(set(review_terms)) if review_terms else "No review terms identified")

    # ✅ PATCH: POSITIVE OUTPUT (ignored downstream)
    st.subheader("Positive Terms (System Only - Not Used)")
    st.write(sorted(set(positive_terms)) if positive_terms else "No positives identified")

    st.subheader("Search-Term Negatives")
    st.write(sorted(set(search_term_negatives)))

    st.subheader("AI Root Negatives")
    st.write(sorted(set(ai_roots)))

    st.subheader("AI Variations")
    st.write(sorted(set(ai_variations)))

    st.subheader("Final Google Ads Negative List")

    st.text_area(
        "Copy & Paste",
        "\n".join(final),
        height=500
    )

    st.download_button(
        "Download TXT",
        "\n".join(final),
        file_name="negatives.txt"
    )
