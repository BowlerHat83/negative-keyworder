import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import time

# -------------------------
# CONFIG
# -------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

st.title("Negative Keyworder")

# -------------------------
# STATE SAFETY LOCKS
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


def chunk_list(lst, size=200):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def safe_generate(prompt):
    """Wrapper to prevent quota crash from killing app"""
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

uploaded_file = st.file_uploader("Upload Search Terms CSV", type=["csv"])

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    if not df.empty:
        col = df.columns[0]
        st.session_state.search_terms = "\n".join(
            df[col].dropna().astype(str).tolist()
        )

# -------------------------
# RUN BUTTON
# -------------------------
run = st.button("Analyse Search Terms", disabled=st.session_state.running)

if run:

    if st.session_state.running:
        st.warning("Already running. Please wait.")
        st.stop()

    if not st.session_state.search_terms.strip():
        st.error("Please upload a CSV first.")
        st.stop()

    terms = st.session_state.search_terms.split("\n")

    # ---- INPUT HASH (prevents duplicate API calls)
    input_signature = (
        target_keywords +
        landing_page +
        "\n".join(terms)
    )
    current_hash = hash_input(input_signature)

    # ---- CACHE CHECK
    if current_hash == st.session_state.last_run_hash:
        st.success("Using cached result (no API call).")
        st.text_area("Copy & Paste", st.session_state.last_output, height=400)
        st.stop()

    st.session_state.running = True

    st.info(f"Processing {len(terms)} terms in chunks...")

    outputs = []

    # -------------------------
    # CHUNKED PROCESSING (CRITICAL FIX)
    # -------------------------
    for i, chunk in enumerate(chunk_list(terms, 200)):

        prompt = f"""
You are a Google Ads negative keyword generator.

Return ONLY copy-paste formatted keywords.

FORMAT:
broad: keyword
phrase: "keyword"
exact: [keyword]

RULES:
- one per line
- no explanation
- no JSON
- no markdown
- choose correct match type when needed
- NEVER default to exact unless necessary
- competitor brands should be BROAD negatives

TARGET KEYWORDS:
{target_keywords if target_keywords.strip() else "None"}

LANDING PAGE:
{landing_page}

SEARCH TERMS CHUNK {i+1}:
{chr(10).join(chunk)}
"""

        st.write(f"Processing chunk {i+1} / {len(list(chunk_list(terms, 200)))}")

        result = safe_generate(prompt)
        outputs.append(result)

        # small delay to reduce quota bursts
        time.sleep(1.2)

    raw_output = "\n".join(outputs)

    # -------------------------
    # SAVE CACHE
    # -------------------------
    st.session_state.last_run_hash = current_hash
    st.session_state.last_output = raw_output
    st.session_state.running = False

    # -------------------------
    # OUTPUT
    # -------------------------
    st.subheader("Google Ads Paste Format")

    st.text_area("Copy & Paste", raw_output, height=400)

    st.download_button(
        "Download TXT",
        raw_output,
        file_name="negative_keywords.txt",
        mime="text/plain"
    )
