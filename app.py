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
    "last_run_hash": None,
    "last_output": "",
    "last_brand_analysis": "",
    "running": False,
    "search_terms": ""
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# -------------------------
# HELPERS
# -------------------------
def hash_input(text):
    return hashlib.md5(text.encode()).hexdigest()


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def safe_generate(prompt):
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace("```", "")
    except Exception as e:
        return f"Error: {str(e)}"


# -------------------------
# BRAND ANALYSIS (SAFE - STILL OK AS IT DOES NOT GENERATE KEYWORDS)
# -------------------------
def analyse_brand_positioning(page_text):
    prompt = f"""
Return STRICT JSON ONLY:

{{
  "summary": "short brand summary",
  "premium_brand": "yes",
  "budget_friendly": "no",
  "enterprise_focused": "yes",
  "education_friendly": "no"
}}

CONTENT:
{page_text[:4000]}
"""
    return safe_generate(prompt)


def parse_brand(json_text):
    try:
        data = json.loads(json_text)
        return {
            "premium": str(data.get("premium_brand", "no")).lower() == "yes",
            "budget": str(data.get("budget_friendly", "no")).lower() == "yes",
            "education": str(data.get("education_friendly", "no")).lower() == "yes",
        }
    except Exception:
        return {"premium": False, "budget": False, "education": False}


# -------------------------
# SCRAPE
# -------------------------
def scrape_page_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        for s in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
            s.extract()

        parts = []

        if soup.title:
            parts.append(soup.title.get_text(" ", strip=True))

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            parts.append(meta.get("content"))

        for tag in soup.find_all(["h1", "h2", "h3"]):
            parts.append(tag.get_text(" ", strip=True))

        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) > 40:
                parts.append(text)

        return re.sub(r"\s+", " ", " ".join(parts))[:6000]

    except Exception:
        return ""


# -------------------------
# NO HALLUCINATION CLASSIFIER (CORE CHANGE)
# -------------------------
def classify_term(term, brand_context, campaign_type):
    prompt = f"""
You are a STRICT Google Ads keyword classifier.

CRITICAL RULES:
- You MUST ONLY evaluate the given term
- You MUST NOT invent or suggest new keywords
- You MUST NOT generalise
- You MUST NOT rephrase
- Output ONLY ONE WORD: KEEP or NEGATIVE

TERM:
{term}

BRAND:
{brand_context}

CAMPAIGN:
{campaign_type}
"""
    result = safe_generate(prompt).strip().upper()

    if "NEGATIVE" in result:
        return "NEGATIVE"
    return "KEEP"


# -------------------------
# GOOGLE ADS FORMAT
# -------------------------
def format_google_ads_negatives(terms):
    formatted = []
    for t in terms:
        t = t.strip()
        if not t:
            continue

        if " " in t:
            formatted.append(f'-"{t}"')
        else:
            formatted.append(f"-{t}")

    return sorted(set(formatted))


# -------------------------
# INPUTS
# -------------------------
target_keywords = st.text_area("Enter Target Keywords", height=150)
landing_page = st.text_input("Landing Page URL *")

campaign_type = st.selectbox(
    "Campaign Type *",
    ["Select campaign type", "Search", "Shopping", "Display", "Performance Max", "Video", "Demand Gen"]
)

uploaded_file = st.file_uploader("Upload Search Terms CSV *", type=["csv"])


if uploaded_file:
    df = pd.read_csv(uploaded_file, encoding="utf-8", on_bad_lines="skip", engine="python")

    if df.empty:
        st.error("CSV empty")
        st.stop()

    col = st.selectbox("Select Column", df.columns)

    st.session_state.search_terms = "\n".join(
        df[col].dropna().astype(str).tolist()
    )


# -------------------------
# VALIDATION
# -------------------------
def validate_inputs():
    if not landing_page.strip():
        st.error("Missing URL")
        return False
    if campaign_type == "Select campaign type":
        st.error("Select campaign type")
        return False
    if uploaded_file is None:
        st.error("Upload CSV")
        return False
    if not st.session_state.search_terms.strip():
        st.error("CSV empty")
        return False
    return True


# -------------------------
# RUN
# -------------------------
run = st.button("Analyse Search Terms", disabled=st.session_state.running)

if run:

    st.session_state.running = True

    if not validate_inputs():
        st.stop()

    # -------------------------
    # SCRAPE
    # -------------------------
    page_text = scrape_page_text(landing_page)

    # -------------------------
    # BRAND
    # -------------------------
    brand_raw = analyse_brand_positioning(page_text)

    # -------------------------
    # TERMS
    # -------------------------
    terms = list(set([
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]))

    # -------------------------
    # HARD RULES (SAFE FILTER)
    # -------------------------
    hard_rules = ["jobs","job","career","careers","salary","hiring","login","portal","reddit","youtube"]

    remaining = []
    local_negatives = set()

    for t in terms:
        if any(re.search(rf"\b{w}\b", t) for w in hard_rules):
            local_negatives.add(t)
        else:
            remaining.append(t)

    # -------------------------
    # AI CLASSIFICATION LOOP (NO HALLUCINATION)
    # -------------------------
    ai_negatives = []

    progress = st.progress(0)
    status = st.empty()

    for i, term in enumerate(remaining):

        progress.progress(int((i + 1) / len(remaining) * 100))
        status.info(f"Classifying {i+1} of {len(remaining)}")

        decision = classify_term(term, brand_raw, campaign_type)

        if decision == "NEGATIVE":
            ai_negatives.append(term)

        time.sleep(0.05)

    # -------------------------
    # MERGE (ALL FROM INPUT ONLY)
    # -------------------------
    combined = ai_negatives + list(local_negatives)

    # NO AI GENERATION HERE ANYMORE
    final = sorted(set(combined))

    # -------------------------
    # OUTPUT FORMAT
    # -------------------------
    output = "\n".join(format_google_ads_negatives(final))

    # -------------------------
    # OUTPUT
    # -------------------------
    st.success("Analysis Complete")

    st.subheader("Final Negatives (NO HALLUCINATION MODE)")
    st.text_area("Copy & Paste", output, height=500)

    st.download_button(
        "Download TXT",
        output,
        file_name="negative_keywords.txt",
        mime="text/plain"
    )

    st.session_state.last_output = output
