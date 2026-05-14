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
target_keywords = st.text_area(
    "Enter Target Keywords",
    height=150
)

landing_page = st.text_input(
    "Landing Page URL"
)

# -------------------------
# CAMPAIGN CONTEXT
# -------------------------
st.subheader("Campaign Context")

campaign_type = st.selectbox(
    "Campaign Type",
    [
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

protect_keywords = st.checkbox(
    "Protect searches closely related to target keywords",
    value=True
)

# -------------------------
# FILE UPLOAD
# -------------------------
uploaded_file = st.file_uploader(
    "Upload Search Terms CSV",
    type=["csv"]
)

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
# RUN BUTTON
# -------------------------
run = st.button(
    "Analyse Search Terms",
    disabled=st.session_state.running
)

if run:

    if st.session_state.running:
        st.warning("Already running. Please wait.")
        st.stop()

    if not st.session_state.search_terms.strip():
        st.error("Please upload a CSV first.")
        st.stop()

    # -------------------------
    # CLEAN TERMS
    # -------------------------
    terms = [
        t.strip().lower()
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]

    # Remove duplicates
    terms = list(set(terms))

    # -------------------------
    # LOCAL NEGATIVE FILTERING
    # -------------------------
    local_negatives = set()

    obvious_negative_words = [
        "jobs",
        "job",
        "career",
        "careers",
        "salary",
        "hiring",
        "free",
        "cheap",
        "login",
        "portal",
        "template",
        "sample",
        "example",
        "reddit",
        "youtube",
        "pdf",
        "guide",
    ]

    remaining_terms = []

    for term in terms:

        # Auto-process obvious negatives locally
        if any(word in term for word in obvious_negative_words):

            # Google Ads broad negative format
            local_negatives.add(term)

        else:
            remaining_terms.append(term)

    # -------------------------
    # INPUT HASH
    # -------------------------
    input_signature = (
        target_keywords +
        landing_page +
        campaign_type +
        allow_competitors +
        str(protect_keywords) +
        "\n".join(remaining_terms)
    )

    current_hash = hash_input(input_signature)

    # -------------------------
    # CACHE CHECK
    # -------------------------
    if current_hash == st.session_state.last_run_hash:

        st.success("Using cached result (no API call).")

        st.text_area(
            "Copy & Paste",
            st.session_state.last_output,
            height=400
        )

        st.stop()

    st.session_state.running = True

    st.info(
        f"""
Processing:
- {len(terms)} uploaded terms
- {len(local_negatives)} handled locally
- {len(remaining_terms)} sent to Gemini
"""
    )

    outputs = []

    chunks = list(chunk_list(remaining_terms, 200))

    # -------------------------
    # CHUNKED AI PROCESSING
    # -------------------------
    for i, chunk in enumerate(chunks):

        prompt = f"""
You are a Google Ads negative keyword generator.

Return ONLY copy-paste formatted negative keywords.

FORMAT:
keyword
"keyword"
[keyword]

RULES:
- one keyword per line
- broad match = plain keyword only
- phrase match = wrapped in quotation marks
- exact match = wrapped in square brackets
- no labels like broad:, phrase:, exact:
- no explanations
- no markdown
- no bullets
- no numbering

MATCH TYPE RULES:
- broad = default for most negatives
- competitor brands should usually be broad negatives
- phrase = only when word order matters
- exact = only when precision is critical
- if unsure, use broad

CAMPAIGN CONTEXT:
- Campaign Type: {campaign_type}
- Competitor Targeting: {allow_competitors}
- Protect Core Keywords: {protect_keywords}

CHANNEL-SPECIFIC RULES:

SEARCH:
- aggressively negative irrelevant intent
- preserve high commercial intent searches

SHOPPING:
- preserve product-specific searches
- preserve SKU/model searches
- negative informational traffic aggressively

DISPLAY:
- negative low-quality placements and informational intent
- allow broader audience discovery

PERFORMANCE MAX:
- preserve mixed-intent commercial searches
- avoid over-negativing discovery traffic

VIDEO:
- negative non-relevant educational traffic
- preserve awareness-stage commercial intent

DEMAND GEN:
- preserve mid-funnel and discovery intent
- avoid over-restricting broader commercial audiences

IMPORTANT STRATEGIC RULES:
- If competitor targeting is enabled, avoid negativing competitor brand searches unless clearly irrelevant
- Protect searches closely aligned with target keywords if keyword protection is enabled
- Match negatives to the selected campaign type strategy

TARGET KEYWORDS:
{target_keywords if target_keywords.strip() else "None"}

LANDING PAGE:
{landing_page}

SEARCH TERMS:
{chr(10).join(chunk)}
"""

        st.write(f"Processing chunk {i+1} / {len(chunks)}")

        result = safe_generate(prompt)

        outputs.append(result)

        # Small delay to reduce quota bursts
        time.sleep(1.2)

    # -------------------------
    # COMBINE LOCAL + AI OUTPUT
    # -------------------------
    ai_output = "\n".join(outputs)

    local_output = "\n".join(sorted(local_negatives))

    raw_output = local_output + "\n" + ai_output

    # Remove accidental duplicate lines
    raw_output = "\n".join(
        sorted(set(
            line.strip()
            for line in raw_output.split("\n")
            if line.strip()
        ))
    )

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

    st.text_area(
        "Copy & Paste",
        raw_output,
        height=500
    )

    st.download_button(
        "Download TXT",
        raw_output,
        file_name="negative_keywords.txt",
        mime="text/plain"
    )
