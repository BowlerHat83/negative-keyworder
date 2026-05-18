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

st.set_page_config(page_title="Negative Keyworder V3", layout="wide")
st.title("Negative Keyworder V3")

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
    return re.sub(r"\s+", " ", t.strip().lower())


def safe_generate(prompt):
    try:
        r = model.generate_content(prompt)
        return {"ok": True, "text": r.text.strip().replace("```", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def extract_json(text):
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
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

    result = safe_generate(prompt)

    if not result["ok"]:
        return None, result["error"]

    data = extract_json(result["text"])

    if not data:
        return {
            "summary": "unknown",
            "positioning": "mixed",
            "core_offerings": [],
            "safe_roots": []
        }, None

    return data, None


# -------------------------
# LAYER 2: INTENT CLASSIFICATION
# -------------------------
def classify_term(term, brand_context, target_keywords):

    prompt = f"""
You are a PPC analyst.

Return ONLY:
NEGATIVE | POSITIVE | REVIEW

RULE:
- NEGATIVE = irrelevant
- POSITIVE = relevant
- REVIEW = uncertain

TERM:
{term}

BRAND:
{brand_context}

TARGET:
{target_keywords}
"""

    result = safe_generate(prompt)

    if not result["ok"]:
        return None, result["error"]

    text = result["text"].upper()

    if "NEGATIVE" in text:
        return "NEGATIVE", None
    if "POSITIVE" in text:
        return "POSITIVE", None
    return "REVIEW", None


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
# LAYER 3.5: VARIATIONS
# -------------------------
def expand_variations(negatives):

    prompt = f"""
Expand ONLY semantic or plural variations.

RULES:
- NO invention
- ONLY close variants
- one per line

NEGATIVES:
{negatives[:200]}
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
# FORMAT GOOGLE ADS
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
        return "Select campaign type"
    if not landing_page.strip():
        return "Missing landing page"
    if uploaded_file is None:
        return "Missing CSV"
    if not st.session_state.search_terms.strip():
        return "Missing search terms"
    return None


# -------------------------
# UI ERROR DISPLAY
# -------------------------
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
        page_text = scrape_page(landing_page)

    with st.spinner("Building brand model..."):
        brand, err = brand_model(page_text, target_keywords)

        if err:
            st.session_state.error_message = (
                "⚠️ Gemini quota reached or API error. Please try again later."
            )
            st.stop()

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
    # BUCKETS
    # -------------------------
    search_term_negatives = []
    review_terms = []

    progress = st.progress(0)
    status = st.empty()

    # -------------------------
    # LAYER 2 PROCESSING
    # -------------------------
    for i, t in enumerate(terms):

        progress.progress(int((i + 1) / len(terms) * 100))
        status.info(f"Processing {i+1}/{len(terms)}")

        decision, err = classify_term(t, brand, target_keywords)

        if err:
            st.session_state.error_message = (
                "⚠️ Gemini quota reached or API error. Please try again later."
            )
            st.stop()

        if decision == "NEGATIVE":
            search_term_negatives.append(t)

        elif decision == "REVIEW":
            review_terms.append(t)

    # -------------------------
    # LAYER 3 ROOTS
    # -------------------------
    ai_roots = []
    for t in search_term_negatives:
        ai_roots.extend(extract_roots(t, protected_roots))

    # -------------------------
    # LAYER 3.5 VARIATIONS
    # -------------------------
    ai_variations = expand_variations(search_term_negatives)

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
