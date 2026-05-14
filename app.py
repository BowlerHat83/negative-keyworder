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

st.set_page_config(page_title="Negative Keyworder V2", layout="wide")
st.title("Negative Keyworder V2")

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
            return "⚠️ Quota exceeded. Please wait or upgrade API plan."
        return f"Error: {str(e)}"


# -------------------------
# 🔥 STRONG PPC DEDUPE (RESTORED)
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
# INPUTS
# -------------------------
target_keywords = st.text_area("Enter Target Keywords", height=150)
landing_page = st.text_input("Landing Page URL *")

st.subheader("Campaign Context")

campaign_type = st.selectbox(
    "Campaign Type *",
    [
        "Select campaign type",
        "Search",
        "Shopping",
        "Display",
        "Performance Max",
        "Video",
        "Demand Gen"
    ]
)

allow_competitors = st.radio(
    "Target Competitor Searches?",
    ["Yes", "No"],
    horizontal=True
)

# -------------------------
# DYNAMIC UI
# -------------------------
shopping_feed = ""
audience_signal = ""
placement_exclusions = ""

if campaign_type == "Shopping":
    shopping_feed = st.text_input("Primary Product Category")

elif campaign_type == "Display":
    placement_exclusions = st.text_area("Placement Exclusions / Notes")

elif campaign_type in ["Performance Max", "Demand Gen"]:
    audience_signal = st.text_area("Audience Signals / Interests")


# -------------------------
# FILE UPLOAD
# -------------------------
uploaded_file = st.file_uploader("Upload Search Terms CSV *", type=["csv"])

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
    # CLEAN TERMS
    # -------------------------
    terms = [
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]
    terms = list(set(terms))

    obvious_negative_words = [
        "jobs","job","career","careers","salary",
        "hiring","free","cheap","login","portal",
        "template","sample","example","reddit",
        "youtube","pdf","guide"
    ]

    local_negatives = set()
    remaining_terms = []

    for term in terms:
        if any(word in term for word in obvious_negative_words):
            local_negatives.add(term)
        else:
            remaining_terms.append(term)

    # -------------------------
    # CACHE (FIXED ✔ INPUT-BASED)
    # -------------------------
    input_signature = (
        target_keywords +
        landing_page +
        campaign_type +
        allow_competitors +
        shopping_feed +
        audience_signal +
        placement_exclusions +
        "\n".join(remaining_terms)
    )

    current_hash = hash_input(input_signature)

    if current_hash == st.session_state.last_run_hash:
        st.success("Using cached result (no API call).")
        st.text_area("Copy & Paste", st.session_state.last_output, height=500)
        st.stop()

    # -------------------------
    # PROGRESS UI
    # -------------------------
    chunks = list(chunk_list(remaining_terms, 150))
    total_chunks = max(len(chunks), 1)

    progress_bar = st.progress(0)
    status_text = st.empty()

    outputs = []

    # -------------------------
    # 🔥 STRONG PPC PROMPT (RESTORED)
    # -------------------------
    for i, chunk in enumerate(chunks):

        progress_bar.progress(int(((i + 1) / total_chunks) * 100))
        status_text.info(f"Processing chunk {i+1} of {total_chunks}...")

        prompt = f"""
You are a senior Google Ads PPC strategist.

TASK:
Analyse search terms and return ONLY negative keywords.

CRITICAL RULES:
- Protect ALL commercial intent
- Do NOT remove terms unless clearly irrelevant
- NEVER over-block broad discovery traffic
- Only generalise when intent is identical
- If unsure → DO NOT include as negative

NEGATIVE KEYWORD RULES:
- Use broad match where safe
- Use phrase only if word order matters
- Use exact only for high precision exclusions

DO NOT:
- Invent keywords
- Over-generalise categories
- Remove revenue-generating intent

CAMPAIGN TYPE:
{campaign_type}

COMPETITOR TARGETING:
{allow_competitors}

SEARCH TERMS:
{chr(10).join(chunk)}

OUTPUT:
Only negative keywords, one per line.
No explanations.
No formatting.
"""

        with st.spinner("Analysing search intent..."):
            result = safe_generate(prompt)

        outputs.append(result)
        time.sleep(0.1)

    # -------------------------
    # MERGE
    # -------------------------
    ai_output = "\n".join(outputs)

    ai_lines = clean_output_lines(ai_output.split("\n"))
    local_lines = clean_output_lines(list(local_negatives))

    combined = ai_lines + local_lines

    final_output = semantic_dedupe(combined)

    raw_output = "\n".join(final_output)

    # -------------------------
    # CACHE SAVE (FIXED ✔)
    # -------------------------
    st.session_state.last_run_hash = current_hash
    st.session_state.last_output = raw_output
    st.session_state.running = False

    progress_bar.empty()
    status_text.empty()

    st.success("Analysis Complete")

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
