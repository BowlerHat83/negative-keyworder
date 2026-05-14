import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import time
import re

# -------------------------
# CONFIG
# -------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

st.title("Negative Keyworder")

# -------------------------
# STATE
# -------------------------
if "last_run_hash" not in st.session_state:
    st.session_state.last_run_hash = None

if "last_output" not in st.session_state:
    st.session_state.last_output = ""

if "running" not in st.session_state:
    st.session_state.running = False


# -------------------------
# HELPERS
# -------------------------
def hash_input(text):
    return hashlib.md5(text.encode()).hexdigest()


def chunk_list(lst, size=250):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def safe_generate(prompt):
    try:
        return model.generate_content(prompt).text.strip()
    except Exception as e:
        if "429" in str(e):
            return "⚠️ Quota exceeded. Please wait or upgrade API plan."
        return f"Error: {str(e)}"


# -------------------------
# INPUTS
# -------------------------
target_keywords = st.text_area("Enter Target Keywords", height=150)
landing_page = st.text_input("Landing Page URL")

st.subheader("Campaign Context")

campaign_type = st.selectbox(
    "Campaign Type",
    ["Search", "Shopping", "Display", "Performance Max", "Video", "Demand Gen"]
)

allow_competitors = st.radio(
    "Target Competitor Searches?",
    ["Yes", "No"],
    horizontal=True
)

# -------------------------
# FILE UPLOAD
# -------------------------
uploaded_file = st.file_uploader("Upload Search Terms CSV", type=["csv"])

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    st.success(f"{len(df)} search terms uploaded")

    if not df.empty:
        col = df.columns[0]
        st.session_state.search_terms = "\n".join(
            df[col].dropna().astype(str).tolist()
        )


# -------------------------
# RUN
# -------------------------
run = st.button("Analyse Search Terms", disabled=st.session_state.running)

if run:

    if not st.session_state.search_terms.strip():
        st.error("Please upload a CSV first.")
        st.stop()

    # -------------------------
    # CLEAN TERMS
    # -------------------------
    terms = [normalize(t) for t in st.session_state.search_terms.split("\n") if t.strip()]
    terms = list(set(terms))

    # -------------------------
    # LOCAL HARD FILTER (ONLY OBVIOUS WASTE)
    # -------------------------
    obvious_negative_words = [
        "jobs", "job", "career", "careers", "salary",
        "hiring", "free", "cheap", "login", "portal",
        "template", "sample", "example", "reddit",
        "youtube", "pdf", "guide"
    ]

    local_negatives = set()
    remaining_terms = []

    for term in terms:
        if any(word in term for word in obvious_negative_words):
            local_negatives.add(term)
        else:
            remaining_terms.append(term)

    # -------------------------
    # CACHE INPUT
    # -------------------------
    input_signature = (
        target_keywords +
        landing_page +
        campaign_type +
        allow_competitors +
        "\n".join(remaining_terms)
    )

    current_hash = hash_input(input_signature)

    if current_hash == st.session_state.last_run_hash:
        st.success("Using cached result (no API call).")
        st.text_area("Copy & Paste", st.session_state.last_output, height=400)
        st.stop()

    st.session_state.running = True

    st.info(f"""
Processing:
- {len(terms)} total terms
- {len(local_negatives)} removed locally
- {len(remaining_terms)} sent to AI
""")

    outputs = []
    chunks = list(chunk_list(remaining_terms, 250))

    # -------------------------
    # AI PROCESSING
    # -------------------------
    for i, chunk in enumerate(chunks):

        prompt = f"""
You are a senior PPC negative keyword strategist.

CRITICAL RULE:
All outputs MUST originate from the provided search terms.
You are ONLY allowed to:
- remove noise
- merge duplicate intent
- compress variations that clearly share identical meaning

You are NOT allowed to invent new concepts outside the data.

-------------------------
TASK
-------------------------
1. Identify shared INTENT across search terms
2. Merge only when intent is identical
3. Convert to MINIMAL ROOT NEGATIVES

-------------------------
CAMPAIGN CONTEXT
-------------------------
Campaign Type: {campaign_type}
Competitor Targeting: {allow_competitors}

-------------------------
RULES
-------------------------
- output ONLY negative keywords
- one per line
- broad match default
- phrase only if necessary
- exact only for precision cases
- DO NOT list variations if already covered by a root term
- DO NOT over-generalise unrelated terms
- NO explanations

-------------------------
CRITICAL SAFETY RULE
-------------------------
Only merge terms if they clearly represent the SAME INTENT.
If there is ambiguity (e.g. "conduit fittings" vs "electrical conduit"),
DO NOT merge them.

-------------------------
DATA
-------------------------
TARGET KEYWORDS:
{target_keywords or "None"}

LANDING PAGE:
{landing_page}

SEARCH TERMS:
{chr(10).join(chunk)}
"""

        st.write(f"Processing chunk {i+1}/{len(chunks)}")

        result = safe_generate(prompt)

        if "⚠️ Quota exceeded" in result:
            st.error(result)
            st.session_state.running = False
            st.stop()

        outputs.append(result)
        time.sleep(1.2)

    # -------------------------
    # MERGE OUTPUT
    # -------------------------
    ai_output = "\n".join(outputs)
    local_output = "\n".join(sorted(local_negatives))

    raw_output = local_output + "\n" + ai_output

    # DEDUPE
    raw_output = "\n".join(
        sorted(set(line.strip() for line in raw_output.split("\n") if line.strip()))
    )

    # -------------------------
    # CACHE SAVE
    # -------------------------
    st.session_state.last_run_hash = current_hash
    st.session_state.last_output = raw_output
    st.session_state.running = False

    # -------------------------
    # OUTPUT
    # -------------------------
    st.subheader("Google Ads Paste Format")

    st.text_area("Copy & Paste", raw_output, height=500)

    st.download_button(
        "Download TXT",
        raw_output,
        file_name="negative_keywords.txt",
        mime="text/plain"
    )
