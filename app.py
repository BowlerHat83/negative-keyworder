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

st.set_page_config(
    page_title="Negative Keyworder V3",
    layout="wide"
)

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


# -------------------------
# OPTION 1: REPLACED safe_generate()
# -------------------------
def safe_generate(prompt, retries=3, delay=2):
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            return text.replace("```", "").strip()

        except Exception as e:
            if "429" in str(e):
                time.sleep(delay * (attempt + 1))
                continue
            return f"Error: {str(e)}"

    return "⚠️ Failed after retries."


# -------------------------
# GOOGLE ADS FORMATTING
# -------------------------
def format_google_ads_negatives(terms):
    formatted = []

    for t in terms:
        t = t.strip()
        if not t:
            continue

        # phrase match formatting
        if " " in t:
            formatted.append(f'-"{t}"')
        else:
            formatted.append(f"-{t}")

    return sorted(set(formatted))


# -------------------------
# SEMANTIC DEDUPE
# -------------------------
def semantic_dedupe(negatives):
    prompt = f"""
You are a senior PPC account strategist.

TASK:
Deduplicate a negative keyword list WITHOUT damaging coverage.

CRITICAL RULES:
- Never over-generalise
- Only merge if intent is IDENTICAL
- If unsure → KEEP BOTH
- Protect commercial intent safety first

MERGE ONLY WHEN SAFE:
- "jobs", "crm jobs", "sales jobs" → jobs
- "free crm", "crm free software" → free

DO NOT MERGE:
- "metal brackets" vs "metal conduit"
- "electrical conduit" vs "conduit fittings"

OUTPUT RULES:
- ONLY final keywords
- one per line
- no explanations
- no markdown

NEGATIVES:
{chr(10).join(negatives)}
"""

    result = safe_generate(prompt)
    cleaned = clean_output_lines(result.split("\n"))
    return sorted(set(cleaned))


# -------------------------
# SCRAPE LANDING PAGE
# -------------------------
def scrape_page_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        for s in soup(["script", "style", "noscript", "svg", "footer", "nav"]):
            s.extract()

        content_parts = []

        if soup.title:
            content_parts.append(soup.title.get_text(" ", strip=True))

        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            content_parts.append(meta.get("content"))

        for tag in soup.find_all(["h1", "h2", "h3"]):
            text = tag.get_text(" ", strip=True)
            if text:
                content_parts.append(text)

        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) > 40:
                content_parts.append(text)

        combined = " ".join(content_parts)
        combined = re.sub(r"\s+", " ", combined)

        return combined[:6000]

    except Exception:
        return ""


# -------------------------
# BRAND POSITIONING
# -------------------------
def analyse_brand_positioning(page_text):
    prompt = f"""
You are a PPC strategist.

Analyse the landing page positioning.

Return STRICT VALID JSON ONLY.

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

    result = safe_generate(prompt)
    result = result.replace("```json", "").replace("```", "")
    return result.strip()


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
selected_column = None

if uploaded_file:
    df = pd.read_csv(uploaded_file, encoding="utf-8", on_bad_lines="skip", engine="python")

    if df.empty:
        st.error("CSV appears empty.")
        st.stop()

    st.success(f"{len(df)} rows uploaded")

    selected_column = st.selectbox("Select Search Term Column", df.columns)

    st.session_state.search_terms = "\n".join(
        df[selected_column].dropna().astype(str).tolist()
    )


# -------------------------
# VALIDATION
# -------------------------
def validate_inputs():
    if not landing_page.strip():
        st.error("Please enter a Landing Page URL.")
        return False

    if campaign_type == "Select campaign type":
        st.error("Please select a Campaign Type.")
        return False

    if uploaded_file is None:
        st.error("Please upload a Search Terms CSV.")
        return False

    if not st.session_state.search_terms.strip():
        st.error("CSV appears empty.")
        return False

    return True


# -------------------------
# RUN
# -------------------------
run = st.button("Analyse Search Terms", disabled=st.session_state.running)

if run:

    st.session_state.running = True

    if not validate_inputs():
        st.session_state.running = False
        st.stop()

    # -------------------------
    # SCRAPE PAGE
    # -------------------------
    with st.spinner("Analysing landing page..."):
        page_text = scrape_page_text(landing_page)

    if not page_text:
        st.warning("Could not fully scrape landing page.")

    # -------------------------
    # BRAND ANALYSIS
    # -------------------------
    with st.spinner("Analysing brand positioning..."):
        brand_analysis_raw = analyse_brand_positioning(page_text)

    brand_flags = parse_brand(brand_analysis_raw)

    # -------------------------
    # CLEAN TERMS
    # -------------------------
    terms = list(set([
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]))

    hard_rules = [
        "jobs","job","career","careers","salary","hiring",
        "login","portal","reddit","youtube"
    ]

    contextual = []
    if brand_flags["premium"]:
        contextual += ["cheap","budget","discount"]
    if not brand_flags["education"]:
        contextual += ["course","tutorial"]

    local_negatives = set()
    remaining = []

    for t in terms:
        if any(re.search(rf"\b{w}\b", t) for w in hard_rules + contextual):
            local_negatives.add(t)
        else:
            remaining.append(t)

    # -------------------------
    # CACHE
    # -------------------------
    input_signature = (
        target_keywords +
        landing_page +
        campaign_type +
        allow_competitors +
        brand_analysis_raw +
        "\n".join(remaining)
    )

    current_hash = hash_input(input_signature)

    if current_hash == st.session_state.last_run_hash:
        st.success("Using cached result (no API call).")
        st.text_area("Copy & Paste", st.session_state.last_output, height=500)
        st.stop()

    # -------------------------
    # CHUNKS
    # -------------------------
    chunks = list(chunk_list(remaining, 150))
    outputs = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    # -------------------------
    # AI LOOP
    # -------------------------
    for i, chunk in enumerate(chunks):

        progress_bar.progress(int(((i + 1) / len(chunks)) * 100))
        status_text.info(f"Processing chunk {i+1} of {len(chunks)}...")

        prompt = f"""
You are a senior Google Ads PPC strategist.

TASK:
Return ONLY negative keywords.

BRAND CONTEXT:
{brand_analysis_raw}

CAMPAIGN TYPE:
{campaign_type}

SEARCH TERMS:
{chr(10).join(chunk)}
"""

        result = safe_generate(prompt)
        outputs.append(result)
        time.sleep(0.1)

    # -------------------------
    # MERGE
    # -------------------------
    ai_output = "\n".join(outputs)
    ai_lines = clean_output_lines(ai_output.split("\n"))

    combined = ai_lines + list(local_negatives)

    final = semantic_dedupe(combined)

    # -------------------------
    # GOOGLE ADS FORMAT (NEW)
    # -------------------------
    output = "\n".join(format_google_ads_negatives(final))

    # -------------------------
    # SAVE
    # -------------------------
    st.session_state.last_run_hash = current_hash
    st.session_state.last_output = output
    st.session_state.running = False

    progress_bar.empty()
    status_text.empty()

    # -------------------------
    # OUTPUT
    # -------------------------
    st.success("Analysis Complete")

    st.subheader("Final Negatives (Google Ads Format)")
    st.text_area("Copy & Paste", output, height=500)

    st.download_button(
        "Download TXT",
        output,
        file_name="google_ads_negative_keywords.txt",
        mime="text/plain"
    )

    with st.expander("Brand Debug"):
        st.text(brand_analysis_raw)
