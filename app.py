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

model = genai.GenerativeModel(
    "gemini-2.5-flash"
)

st.set_page_config(
    page_title="Negative Keyworder",
    layout="wide"
)

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


def chunk_list(lst, size=150):
    """
    Smaller chunks improve consistency
    and reduce hallucinated grouping.
    """

    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def normalize(term: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        term.strip().lower()
    )


def clean_output_lines(lines):

    cleaned = []

    for line in lines:

        line = line.strip()

        if not line:
            continue

        # remove bullets/numbers accidentally returned
        line = re.sub(
            r"^[\-\•\d\.\)]\s*",
            "",
            line
        )

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


def semantic_dedupe(negatives):
    """
    Final AI dedupe layer.

    Purpose:
    - remove redundant negatives
    - preserve intent accuracy
    - keep safest root negatives
    - avoid dangerous over-generalisation
    """

    prompt = f"""
You are a senior PPC negative keyword strategist.

Your task:
Semantically deduplicate this negative keyword list.

GOAL:
- remove redundant negatives
- preserve accuracy
- preserve intent precision
- ONLY merge terms when intent is clearly identical

CRITICAL RULES:
- never over-generalise
- do not remove a term if it protects unique intent
- only keep the most efficient root negative
- if uncertain, KEEP BOTH terms

BAD EXAMPLE:
metal
metal conduit
metal brackets

→ BAD because 'metal' is too broad

GOOD EXAMPLE:
jobs
crm jobs
sales jobs
hiring

→ GOOD because 'jobs' safely covers all

GOOD EXAMPLE:
free
free crm
crm free software

→ GOOD because 'free' safely covers all

BAD EXAMPLE:
conduit fittings
electrical conduit

→ BAD because intent may differ

OUTPUT RULES:
- return ONLY final negative keywords
- one per line
- no explanations
- no bullets
- no markdown

NEGATIVES:
{chr(10).join(negatives)}
"""

    result = safe_generate(prompt)

    cleaned = clean_output_lines(
        result.split("\n")
    )

    return sorted(set(cleaned))


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

# -------------------------
# DYNAMIC UI
# -------------------------
shopping_feed = ""
brand_protection = ""
audience_signal = ""
placement_exclusions = ""

if campaign_type == "Shopping":

    shopping_feed = st.text_input(
        "Primary Product Category"
    )

    brand_protection = st.radio(
        "Protect Brand Searches?",
        ["Yes", "No"],
        horizontal=True
    )

elif campaign_type == "Display":

    placement_exclusions = st.text_area(
        "Placement Exclusions / Notes"
    )

elif campaign_type in [
    "Performance Max",
    "Demand Gen"
]:

    audience_signal = st.text_area(
        "Audience Signals / Interests"
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

    st.success(
        f"{len(df)} search terms uploaded"
    )

    if not df.empty:

        col = df.columns[0]

        st.session_state.search_terms = "\n".join(
            df[col]
            .dropna()
            .astype(str)
            .tolist()
        )

# -------------------------
# RUN BUTTON
# -------------------------
run = st.button(
    "Analyse Search Terms",
    disabled=st.session_state.running
)

# -------------------------
# MAIN RUN
# -------------------------
if run:

    if not st.session_state.search_terms.strip():

        st.error(
            "Please upload a CSV first."
        )

        st.stop()

    # -------------------------
    # CLEAN TERMS
    # -------------------------
    terms = [
        normalize(t)
        for t in st.session_state.search_terms.split("\n")
        if t.strip()
    ]

    # dedupe uploaded search terms
    terms = list(set(terms))

    # -------------------------
    # HARD FILTERS
    # -------------------------
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
        "guide"
    ]

    local_negatives = set()
    remaining_terms = []

    for term in terms:

        if any(
            word in term
            for word in obvious_negative_words
        ):

            local_negatives.add(term)

        else:

            remaining_terms.append(term)

    # -------------------------
    # CACHE
    # -------------------------
    input_signature = (
        target_keywords
        + landing_page
        + campaign_type
        + allow_competitors
        + shopping_feed
        + brand_protection
        + audience_signal
        + placement_exclusions
        + "\n".join(remaining_terms)
    )

    current_hash = hash_input(
        input_signature
    )

    if current_hash == st.session_state.last_run_hash:

        st.success(
            "Using cached result (no API call)."
        )

        st.text_area(
            "Copy & Paste",
            st.session_state.last_output,
            height=500
        )

        st.stop()

    st.session_state.running = True

    st.info(f"""
Processing:
- {len(terms)} total terms
- {len(local_negatives)} removed locally
- {len(remaining_terms)} analysed by AI
""")

    outputs = []

    chunks = list(
        chunk_list(
            remaining_terms,
            150
        )
    )

    # -------------------------
    # AI PROCESSING
    # -------------------------
    for i, chunk in enumerate(chunks):

        prompt = f"""
You are a senior PPC search term analyst.

Your job is to review EVERY search term individually.

You must determine:

1. Is the term RELEVANT or IRRELEVANT
2. What is the search INTENT
3. Whether the term should become a NEGATIVE KEYWORD
4. Whether multiple irrelevant terms can safely be compressed into ONE root negative

--------------------------------------------------
IMPORTANT BEHAVIOUR RULES
--------------------------------------------------

- Analyse EACH search term individually first
- Do NOT immediately cluster everything
- Relevance matters more than compression
- Accuracy is more important than reducing keyword count
- Only create root negatives when intent is clearly identical
- ALL negatives must originate from provided search terms
- NEVER invent concepts not present in the data

--------------------------------------------------
ROOT NEGATIVE RULES
--------------------------------------------------

You may compress terms ONLY if:
- the same root word appears repeatedly
- AND the intent is clearly identical
- AND blocking the root will not harm relevant traffic

GOOD:
"jobs", "crm jobs", "crm careers"
→ jobs

GOOD:
"free crm", "crm free software"
→ free

BAD:
"conduit fittings" + "electrical conduit"
→ NOT SAFE TO MERGE

BAD:
"metal brackets" + "metal support beams"
→ NOT SAFE TO MERGE

--------------------------------------------------
CAMPAIGN CONTEXT
--------------------------------------------------

Campaign Type: {campaign_type}

Competitor Targeting: {allow_competitors}

Shopping Feed:
{shopping_feed}

Brand Protection:
{brand_protection}

Audience Signals:
{audience_signal}

Placement Exclusions:
{placement_exclusions}

--------------------------------------------------
CAMPAIGN RULES
--------------------------------------------------

SEARCH:
- preserve commercial buying intent
- remove irrelevant informational traffic

SHOPPING:
- preserve SKU/product searches
- preserve model-specific intent
- remove research traffic aggressively

DISPLAY:
- allow broader discovery intent
- remove obvious low-quality traffic

PERFORMANCE MAX:
- preserve mixed commercial intent
- avoid over-negativing discovery searches

VIDEO:
- preserve awareness intent
- remove irrelevant education intent

DEMAND GEN:
- preserve mid-funnel discovery
- avoid over-filtering

--------------------------------------------------
OUTPUT RULES
--------------------------------------------------

Return ONLY Google Ads negative keywords.

FORMAT:
keyword
"keyword"
[keyword]

RULES:
- one keyword per line
- broad match preferred
- phrase only when word order matters
- exact only if precision is required
- no explanations
- no headings
- no markdown
- no numbering

--------------------------------------------------
TARGET KEYWORDS
--------------------------------------------------

{target_keywords or "None"}

--------------------------------------------------
LANDING PAGE
--------------------------------------------------

{landing_page}

--------------------------------------------------
SEARCH TERMS
--------------------------------------------------

{chr(10).join(chunk)}
"""

        st.write(
            f"Processing chunk {i+1}/{len(chunks)}"
        )

        result = safe_generate(prompt)

        if "⚠️ Quota exceeded" in result:

            st.error(result)

            st.session_state.running = False

            st.stop()

        outputs.append(result)

        time.sleep(1)

    # -------------------------
    # FINAL MERGE
    # -------------------------
    ai_output = "\n".join(outputs)

    ai_lines = clean_output_lines(
        ai_output.split("\n")
    )

    local_lines = clean_output_lines(
        list(local_negatives)
    )

    combined = ai_lines + local_lines

    # -------------------------
    # SEMANTIC DEDUPE
    # -------------------------
    final_output = semantic_dedupe(
        combined
    )

    raw_output = "\n".join(
        final_output
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
    st.subheader(
        "Google Ads Paste Format"
    )

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
