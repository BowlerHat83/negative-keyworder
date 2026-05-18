import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import time
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
def hash_input(text):
    return hashlib.md5(text.encode()).hexdigest()


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
# BRAND POSITIONING (FIXED)
# -------------------------
def analyse_brand_positioning(page_text):

    prompt = f"""
Return ONLY valid JSON.

{{
  "summary": "string",
  "positioning": "premium | budget | enterprise | mixed",
  "core_product_keywords": ["keyword1", "keyword2"]
}}

RULE:
- ONLY extract words that exist in text
- NO invention

TEXT:
{page_text[:4000]}
"""

    raw = safe_generate(prompt)

    parsed = extract_json(raw)

    if parsed:
        return parsed

    return {
        "summary": "unknown",
        "positioning": "mixed",
        "core_product_keywords": []
    }


# -------------------------
# GOOGLE ADS FORMAT
# -------------------------
def format_google_ads(terms):
    out = []

    for t in terms:
        t = t.strip()
        if not t:
            continue

        # Google Ads negative formatting
        if " " in t:
            out.append(f'"{t}"')
        else:
            out.append(t)

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

    hard_rules = {
        "jobs","job","career","careers","salary",
        "hiring","login","portal","youtube","reddit"
    }

    final_terms = []

    # -------------------------
    # SAFE PIPELINE (NO BLANK OUTPUTS)
    # -------------------------
    for t in terms:

        if not t:
            continue

        # skip obvious junk
        if any(w in t for w in hard_rules):
            continue

        # ALWAYS keep original term
        final_terms.append(t)

        # safe decomposition using brand context
        words = t.split()
        for w in words:
            if len(w) > 2:
                final_terms.append(w)

    # -------------------------
    # CONTROLLED AI BOOST (LIMITED HALLUCINATION)
    # -------------------------
    prompt = f"""
Extract ONLY missing keyword variations from this list.

RULES:
- ONLY use words already present
- DO NOT invent new concepts
- OUTPUT single words only

LIST:
{final_terms[:200]}
"""

    ai_extra = safe_generate(prompt)

    ai_words = [
        w.strip().lower()
        for w in ai_extra.split()
        if w.isalpha()
    ]

    final_terms += ai_words[:20]  # hard cap


    # -------------------------
    # FINAL OUTPUT
    # -------------------------
    output = "\n".join(format_google_ads(final_terms))


    # -------------------------
    # UI OUTPUT
    # -------------------------
    st.success("Analysis Complete")

    st.subheader("Brand Positioning (Audit)")
    st.json(brand)

    st.subheader("Final Google Ads Negatives")
    st.text_area("Copy & Paste", output, height=500)

    st.download_button(
        "Download",
        output,
        file_name="negatives.txt"
    )

    st.session_state.last_output = output
