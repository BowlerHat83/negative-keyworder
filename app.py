import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
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
defaults = {
    "last_output": "",
    "search_terms": ""
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# -------------------------
# HELPERS
# -------------------------
def normalize(term):
    return re.sub(r"\s+", " ", term.strip().lower())


def safe_generate(prompt):
    try:
        res = model.generate_content(prompt)
        return res.text.strip().replace("```", "")
    except Exception as e:
        return f"ERROR: {str(e)}"


def extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except:
        return None


# -------------------------
# SCRAPE
# -------------------------
def scrape_page_text(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
            tag.extract()

        text = " ".join([
            soup.title.get_text(" ", strip=True) if soup.title else "",
            " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        ])

        return re.sub(r"\s+", " ", text)[:6000]

    except:
        return ""


# -------------------------
# BRAND POSITIONING (AUDITABLE)
# -------------------------
def analyse_brand_positioning(page_text):

    prompt = f"""
Return ONLY valid JSON.

{{
  "summary": "string",
  "positioning": "premium | budget | enterprise | mixed",
  "tone": "formal | casual | technical | educational",
  "core_keywords": ["word1", "word2"]
}}

IMPORTANT RULE:
- ONLY extract words that exist in the page
- DO NOT invent keywords

TEXT:
{page_text[:4000]}
"""

    raw = safe_generate(prompt)
    data = extract_json(raw)

    return data if data else {
        "summary": "unknown",
        "positioning": "mixed",
        "tone": "unknown",
        "core_keywords": []
    }


# -------------------------
# ROOT PROTECTION SYSTEM
# -------------------------
def build_protected_roots(search_terms, brand_data):
    roots = set()

    for t in search_terms:
        for w in t.split():
            roots.add(w.lower())

    for w in brand_data.get("core_keywords", []):
        roots.add(w.lower())

    return roots


# -------------------------
# SAFE TOKENIZATION
# -------------------------
def safe_tokenize(term, protected_roots):
    tokens = []

    for w in term.split():
        w = w.lower().strip()

        if w in protected_roots:
            continue
        if len(w) <= 2:
            continue

        tokens.append(w)

    return tokens


# -------------------------
# GOOGLE ADS FORMAT
# -------------------------
def format_google_ads(terms):
    out = []

    for t in terms:
        t = t.strip()
        if not t:
            continue

        # Google Ads format (copy/paste safe)
        out.append(f'"{t}"' if " " in t else t)

    return sorted(set(out))


# -------------------------
# INPUTS
# -------------------------
target_keywords = st.text_area("Target Keywords", height=120)
landing_page = st.text_input("Landing Page URL")

campaign_type = st.selectbox(
    "Campaign Type",
    ["Search", "Shopping", "Display", "Performance Max"]
)

uploaded_file = st.file_uploader("Upload CSV", type=["csv"])


if uploaded_file:
    df = pd.read_csv(uploaded_file, engine="python")
    col = st.selectbox("Select Column", df.columns)

    st.session_state.search_terms = "\n".join(
        df[col].dropna().astype(str)
    )


# -------------------------
# VALIDATION
# -------------------------
def validate():
    if not landing_page.strip():
        st.error("Missing URL")
        return False
    if uploaded_file is None:
        st.error("Upload CSV")
        return False
    if not st.session_state.search_terms.strip():
        st.error("No search terms")
        return False
    return True


# -------------------------
# RUN
# -------------------------
if st.button("Analyse"):

    if not validate():
        st.stop()

    # -------------------------
    # SCRAPE + BRAND
    # -------------------------
    page_text = scrape_page_text(landing_page)
    brand = analyse_brand_positioning(page_text)

    # -------------------------
    # TERMS
    # -------------------------
    terms = list(set([
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]))

    protected_roots = build_protected_roots(terms, brand)

    hard_rules = {
        "jobs","job","career","careers","salary",
        "hiring","login","portal","youtube","reddit"
    }

    # -------------------------
    # AUDIT TRACKING
    # -------------------------
    search_term_based = []
    ai_expanded = []
    root_filtered = []

    kept_terms = []

    # -------------------------
    # STEP 1: SEARCH TERM PROCESSING
    # -------------------------
    for t in terms:

        if any(w in t for w in hard_rules):
            root_filtered.append(t)
            continue

        kept_terms.append(t)

        tokens = safe_tokenize(t, protected_roots)

        for w in tokens:
            search_term_based.append(w)

    # -------------------------
    # STEP 2: AI EXPANSION (CONTROLLED)
    # -------------------------
    prompt = f"""
Extract ONLY words that already appear in the list.

RULES:
- NO invention
- NO synonyms
- NO new concepts
- ONLY exact words from input
- one word per line

LIST:
{kept_terms[:200]}
"""

    ai_extra = safe_generate(prompt)

    valid_pool = set(" ".join(kept_terms).split())

    ai_words = [
        w.strip().lower()
        for w in ai_extra.split()
        if w.isalpha() and w.lower() in valid_pool
    ]

    ai_expanded.extend(ai_words[:25])

    # -------------------------
    # FINAL MERGE (CONTROLLED)
    # -------------------------
    all_terms = search_term_based + ai_expanded

    final = format_google_ads(all_terms)

    # -------------------------
    # OUTPUT 1: AUDIT VIEW
    # -------------------------
    st.subheader("Brand Audit")
    st.json(brand)

    st.markdown("### Search-Term Derived Tokens")
    st.write(sorted(set(search_term_based)))

    st.markdown("### AI Expanded Tokens")
    st.write(sorted(set(ai_expanded)))

    st.markdown("### Root Filtered Terms")
    st.write(root_filtered)

    # -------------------------
    # OUTPUT 2: GOOGLE ADS READY
    # -------------------------
    st.subheader("Final Negative Keywords (Google Ads Ready)")

    output = "\n".join(final)

    st.text_area("Copy & Paste", output, height=500)

    st.download_button(
        "Download TXT",
        output,
        file_name="negatives.txt"
    )

    st.session_state.last_output = output
