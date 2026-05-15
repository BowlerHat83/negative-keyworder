import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import time
import re
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
for key in ["last_run_hash", "last_output", "last_brand_analysis", "running"]:
    if key not in st.session_state:
        st.session_state[key] = None if "hash" in key else ""


# -------------------------
# HELPERS
# -------------------------
def hash_input(text):
    return hashlib.md5(text.encode()).hexdigest()


def chunk_list(lst, size=150):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def clean_output_lines(lines):
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[\-\•\d\.\)]\s*", "", line)
        cleaned.append(line)
    return cleaned


def safe_generate(prompt):
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        if "429" in str(e):
            return "⚠️ Quota exceeded."
        return f"Error: {str(e)}"


def extract_flag(text, key):
    match = re.search(rf"{key}=yes", text.lower())
    return bool(match)


# -------------------------
# SCRAPE LANDING PAGE
# -------------------------
def scrape_page_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(response.text, "html.parser")
        for s in soup(["script", "style", "noscript"]):
            s.extract()

        text = soup.get_text(" ")
        return re.sub(r"\s+", " ", text)[:12000]

    except Exception:
        return ""


# -------------------------
# BRAND POSITIONING
# -------------------------
def analyse_brand_positioning(page_text):

    prompt = f"""
You are a PPC strategist.

Return STRICT JSON ONLY:

{{
  "summary": "...",
  "premium_brand": "yes/no",
  "budget_friendly": "yes/no",
  "enterprise_focused": "yes/no",
  "education_friendly": "yes/no"
}}

CONTENT:
{page_text}
"""

    return safe_generate(prompt)


def parse_brand(json_text):
    text = json_text.lower()
    return {
        "premium": "premium_brand" in text and "yes" in text,
        "budget": "budget_friendly" in text and "yes" in text,
        "education": "education_friendly" in text and "yes" in text,
    }


# -------------------------
# INPUTS
# -------------------------
target_keywords = st.text_area("Enter Target Keywords", height=150)
landing_page = st.text_input("Landing Page URL *")

campaign_type = st.selectbox(
    "Campaign Type *",
    ["Select campaign type", "Search", "Shopping", "Display", "Performance Max", "Video", "Demand Gen"]
)

allow_competitors = st.radio("Target Competitor Searches?", ["Yes", "No"], horizontal=True)

uploaded_file = st.file_uploader("Upload Search Terms CSV *", type=["csv"])

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    col = df.columns[0]
    st.session_state.search_terms = "\n".join(df[col].dropna().astype(str).tolist())


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
    return True


# -------------------------
# RUN
# -------------------------
if st.button("Analyse Search Terms"):

    if not validate_inputs():
        st.stop()

    st.session_state.running = True

    # -------------------------
    # BRAND ANALYSIS
    # -------------------------
    page_text = scrape_page_text(landing_page)
    brand_analysis_raw = analyse_brand_positioning(page_text)
    brand_flags = parse_brand(brand_analysis_raw)

    st.subheader("Brand Debug")
    st.write(brand_analysis_raw)

    # -------------------------
    # CLEAN TERMS
    # -------------------------
    terms = list(set([normalize(t) for t in st.session_state.search_terms.split("\n") if t.strip()]))

    hard_rules = [
        "jobs", "job", "career", "careers",
        "salary", "hiring",
        "login", "portal",
        "reddit", "youtube"
    ]

    contextual = []
    if brand_flags["premium"]:
        contextual += ["cheap", "budget", "discount"]
    if not brand_flags["education"]:
        contextual += ["course", "tutorial"]

    local_negatives = set()
    remaining = []

    for t in terms:
        if any(re.search(rf"\b{w}\b", t) for w in hard_rules + contextual):
            local_negatives.add(t)
        else:
            remaining.append(t)

    # -------------------------
    # AI PROCESSING
    # -------------------------
    chunks = list(chunk_list(remaining, 150))
    outputs = []

    for i, chunk in enumerate(chunks):

        prompt = f"""
You are a PPC strategist.

Be conservative.

Only remove clearly non-commercial intent.

BRAND:
{brand_analysis_raw}

SEARCH TERMS:
{chr(10).join(chunk)}

Return negatives only.
"""

        outputs.append(safe_generate(prompt))

    ai_output = "\n".join(outputs)

    ai_lines = clean_output_lines(ai_output.split("\n"))
    final = sorted(set(ai_lines + list(local_negatives)))

    output = "\n".join(final)

    # -------------------------
    # SAVE
    # -------------------------
    st.session_state.last_output = output
    st.session_state.last_brand_analysis = brand_analysis_raw

    st.success("Done")

    # -------------------------
    # OUTPUT
    # -------------------------
    st.subheader("Final Negatives")
    st.text_area("Copy", output, height=500)

    st.subheader("Brand Analysis (debug)")
    st.text(brand_analysis_raw)
