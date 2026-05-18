import streamlit as st
import google.generativeai as genai
import pandas as pd
import re
import json
import requests
from bs4 import BeautifulSoup

# -------------------------
# CONFIG
# -------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

st.set_page_config(page_title="Negative Keyworder V5 (Batch)", layout="wide")
st.title("Negative Keyworder V5 (Batch Optimised)")


# -------------------------
# STATE
# -------------------------
if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""


# -------------------------
# HELPERS
# -------------------------
def normalize(t):
    return re.sub(r"\s+", " ", t.strip().lower())


def safe_generate(prompt):
    try:
        r = model.generate_content(prompt)
        return r.text.strip().replace("```", "")
    except Exception as e:
        return f"ERROR: {str(e)}"


def extract_json(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                return None
    return None


# -------------------------
# SCRAPE LANDING PAGE
# -------------------------
def scrape_page(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        for t in soup(["script", "style", "footer", "nav", "svg"]):
            t.extract()

        text = " ".join([
            soup.title.get_text(" ", strip=True) if soup.title else "",
            " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        ])

        return re.sub(r"\s+", " ", text)[:6000]

    except:
        return ""


# -------------------------
# LAYER 1: BRAND INTELLIGENCE
# -------------------------
def brand_model(page_text, target_keywords):

    prompt = f"""
Return ONLY valid JSON.

Extract:
- summary
- positioning (premium/budget/enterprise/mixed)
- core_offerings (list)
- safe_roots (must NEVER be negatively targeted)

TARGET KEYWORDS:
{target_keywords}

PAGE:
{page_text[:4000]}
"""

    raw = safe_generate(prompt)

    try:
        return json.loads(raw)
    except:
        return {
            "summary": "unknown",
            "positioning": "mixed",
            "core_offerings": [],
            "safe_roots": []
        }


# -------------------------
# LAYER 2: BATCH INTENT CLASSIFICATION (CORE OPTIMISATION)
# -------------------------
def batch_classify_terms(terms, brand_context, target_keywords):

    prompt = f"""
You are a PPC analyst.

Classify each term as:
NEGATIVE | POSITIVE | REVIEW

RULES:
- Default NEGATIVE unless clearly relevant
- REVIEW = uncertain but could risk conversions
- POSITIVE = clearly relevant

Return JSON list ONLY:

[
  {{"term": "...", "label": "NEGATIVE|POSITIVE|REVIEW"}}
]

BRAND CONTEXT:
{brand_context}

TARGET KEYWORDS:
{target_keywords}

TERMS:
{terms}
"""

    raw = safe_generate(prompt)

    data = extract_json(raw)

    if not data:
        return []

    return data


# -------------------------
# LAYER 3: ROOT EXTRACTION
# -------------------------
def extract_roots(term, protected_roots):
    return [
        w.lower()
        for w in term.split()
        if w.lower() not in protected_roots and len(w) > 2
    ]


# -------------------------
# LAYER 3.5: VARIATIONS (SAFE)
# -------------------------
def expand_variations(negatives):

    prompt = f"""
Expand ONLY semantic or plural variations.

RULES:
- NO invention
- ONLY morphological or close semantic variants
- one per line
- max 2 words per line

NEGATIVES:
{negatives[:200]}
"""

    raw = safe_generate(prompt)

    return [
        w.strip().lower()
        for w in raw.split("\n")
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
        out.append(f'"{t}"' if " " in t else t)
    return sorted(set(out))


# -------------------------
# INPUTS
# -------------------------
target_keywords = st.text_area("Target Keywords", height=120)
landing_page = st.text_input("Landing Page URL")

campaign_type = st.selectbox(
    "Campaign Type",
    ["Select", "Search", "Shopping", "PMax", "Display"]
)

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])


if uploaded_file:
    df = pd.read_csv(uploaded_file, engine="python")
    col = st.selectbox("Column", df.columns)

    st.session_state.search_terms = "\n".join(
        df[col].dropna().astype(str)
    )


# -------------------------
# VALIDATION
# -------------------------
def validate():
    if campaign_type == "Select":
        st.error("Select campaign type")
        return False
    if not landing_page.strip():
        st.error("Missing landing page")
        return False
    if uploaded_file is None:
        st.error("Missing CSV")
        return False
    if not st.session_state.search_terms.strip():
        st.error("Missing search terms")
        return False
    return True


# -------------------------
# RUN PIPELINE
# -------------------------
if st.button("Analyse"):

    if not validate():
        st.stop()

    with st.spinner("Scraping landing page..."):
        page_text = scrape_page(landing_page)

    with st.spinner("Building brand model..."):
        brand = brand_model(page_text, target_keywords)

    protected_roots = set(
        normalize(w)
        for w in target_keywords.split()
    )

    protected_roots.update(
        normalize(w)
        for w in brand.get("safe_roots", [])
    )

    # -------------------------
    # LOAD TERMS
    # -------------------------
    terms = [
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]

    # -------------------------
    # LAYER 2: BATCH PROCESSING
    # -------------------------
    BATCH_SIZE = 30

    results = []

    progress = st.progress(0)
    status = st.empty()

    for i in range(0, len(terms), BATCH_SIZE):

        batch = terms[i:i+BATCH_SIZE]

        status.info(f"Processing batch {i//BATCH_SIZE + 1}")

        batch_result = batch_classify_terms(
            batch,
            brand,
            target_keywords
        )

        results.extend(batch_result)

        progress.progress(min(100, int((i / len(terms)) * 100)))

    # -------------------------
    # SPLIT RESULTS
    # -------------------------
    search_term_negatives = []
    review_terms = []

    for r in results:
        if not isinstance(r, dict):
            continue

        term = normalize(r.get("term", ""))
        label = r.get("label", "NEGATIVE")

        if label == "NEGATIVE":
            search_term_negatives.append(term)

        elif label == "REVIEW":
            review_terms.append(term)

    # -------------------------
    # LAYER 3 ROOTS
    # -------------------------
    ai_roots = []
    for t in search_term_negatives:
        ai_roots.extend(extract_roots(t, protected_roots))

    # -------------------------
    # LAYER 3.5 VARIATIONS (includes REVIEW for safety)
    # -------------------------
    ai_variations = expand_variations(
        search_term_negatives + review_terms
    )

    # -------------------------
    # FINAL MERGE
    # -------------------------
    final_raw = search_term_negatives + ai_roots + ai_variations
    final = format_google_ads(final_raw)

    # -------------------------
    # OUTPUTS
    # -------------------------
    st.success("Analysis Complete")

    st.subheader("Brand Positioning Summary")
    st.json(brand)

    st.subheader("Review Queue (Manual Audit Required)")
    st.write(review_terms if review_terms else "No review terms identified")

    st.subheader("Search-Term Negatives")
    st.write(search_term_negatives)

    st.subheader("AI Root Negatives")
    st.write(ai_roots)

    st.subheader("AI Variations")
    st.write(ai_variations)

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
