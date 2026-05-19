import streamlit as st
import pandas as pd
import google.generativeai as genai

from scraper import get_landing_context
from intelli import build_brand_model
from prefilter import contextual_prefilter
from classify import classify_terms_batch
from root import extract_roots_protected
from outputformat import final_classification
from output import build_outputs


# =====================================================
# MODEL
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")


# =====================================================
# APP CONFIG
# =====================================================
st.set_page_config(
    page_title="Negative Keyworder - Final Version",
    layout="wide"
)

st.title("Negative Keyworder - Final Version")


# =====================================================
# SESSION ERROR STATE
# =====================================================
if "error" not in st.session_state:
    st.session_state.error = None


def set_error(code, msg):
    st.session_state.error = f"{code}: {msg}"


def clear_error():
    st.session_state.error = None


if st.session_state.error:
    st.error(st.session_state.error)


# =====================================================
# HELPERS
# =====================================================
def parse_csv(file):

    df = pd.read_csv(file)

    return (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .tolist()
    )


def chunk_list(data, size=100):

    for i in range(0, len(data), size):

        yield data[i:i + size]

def ui_box(title, df=None, text=None):
    st.markdown(f"### {title}")
    
    container = st.container()
    
    with container:
        st.markdown(
            """
            <div style="
                border: 1px solid #333;
                border-radius: 10px;
                padding: 15px;
                background-color: #0e1117;
                margin-bottom: 20px;
            ">
            """,
            unsafe_allow_html=True
        )

        if df is not None:
            st.dataframe(df, use_container_width=True)

        elif text is not None:
            st.text_area("", text, height=300)

        st.markdown("</div>", unsafe_allow_html=True)

def safe_flatten(lst):
    clean = []
    for item in lst:
        if isinstance(item, list):
            clean.extend(item)
        elif item is None:
            continue
        else:
            clean.append(item)
    return clean

# =====================================================
# CLASSIFICATION RULES (DROP-IN REPLACEMENT)
# =====================================================
CLASSIFICATION_RULES = """
You are a strict PPC search term classifier.

=====================================================
HARD DECISION RULE (MOST IMPORTANT)
=====================================================

YOU MUST DEFAULT TO: NEGATIVE

Decision priority:
1. NEGATIVE (default for ALL uncertain cases)
2. POSITIVE (ONLY when extremely clear buying intent exists)
3. REVIEW (ONLY when absolutely unavoidable)

IMPORTANT:
- If you are unsure → ALWAYS choose NEGATIVE
- REVIEW is NOT a safe option
- REVIEW must be extremely rare (<5% of cases)

=====================================================
CRITICAL ANTI-REVIEW BIAS
=====================================================

You are heavily penalised for overusing REVIEW.

Only use REVIEW if ALL are true:
- Term is clearly commercial-adjacent
AND
- Misclassifying as negative would likely remove meaningful revenue
AND
- You cannot confidently decide positive or negative

If ANY condition is missing → classify as NEGATIVE.

=====================================================
NEGATIVE (EXPANDED DEFAULT CLASS)
=====================================================

NEGATIVE includes:
- informational intent
- research / learning intent
- comparison queries
- competitor research
- job/career searches
- DIY / how-to queries
- vague or unclear intent
- low purchase intent
- irrelevant traffic
- accidental searches
- general browsing behavior

DEFAULT RULE:
→ If unsure at ANY point → NEGATIVE

=====================================================
POSITIVE (STRICT FILTER)
=====================================================

Only classify as POSITIVE if ALL apply:
- clear and explicit buying intent
- product or service is directly desired
- high commercial value is obvious
- strong likelihood of conversion

If not 100% confident → DO NOT mark positive

=====================================================
OUTPUT RULES (STRICT)
=====================================================

- Every term MUST be classified
- NO explanations
- NO missing terms
- JSON ONLY output
- REVIEW must be minimal
- NEGATIVE should dominate classification

OUTPUT FORMAT:

{
  "negative": [],
  "review": [],
  "positive": []
}
"""

# =====================================================
# UI STATE MACHINE
# =====================================================
campaign_type = st.selectbox(
    "Campaign Type",
    ["", "Search", "Shopping", "Display", "PMax"]
)

uploaded_file = st.file_uploader(
    "Search Terms CSV",
    type=["csv"]
)

landing_page = None
landing_pages_raw = None
target_keywords = None


# =====================================================
# 🔵 PMAX MODE
# =====================================================
if campaign_type == "PMax":

    landing_pages_raw = st.text_area(
        "Landing Pages (one per line)"
    )


# =====================================================
# 🟡 DISPLAY / SHOPPING MODE
# =====================================================
elif campaign_type in ["Display", "Shopping"]:

    landing_page = st.text_input(
        "Landing Page URL"
    )

    target_keywords = st.text_area(
        "Optional Keywords (used for context)"
    )


# =====================================================
# 🔴 SEARCH MODE
# =====================================================
elif campaign_type == "Search":

    landing_page = st.text_input(
        "Landing Page URL"
    )

    target_keywords = st.text_area(
        "Target Keywords (REQUIRED)"
    )


run = st.button("Run Analysis")

# =====================================================
# RUN PIPELINE
# =====================================================
if run:

    clear_error()

    if not uploaded_file:
        set_error("E001", "Missing search terms CSV")
        st.stop()

    if campaign_type == "":
        set_error("E000", "Please select campaign type")
        st.stop()

    if campaign_type == "PMax" and not landing_pages_raw:
        set_error("E002", "PMax requires landing pages")
        st.stop()

    if campaign_type != "PMax" and not landing_page:
        set_error("E003", "Missing landing page URL")
        st.stop()

    if campaign_type == "Search" and not target_keywords:
        set_error("E004", "Search campaigns require target keywords")
        st.stop()

    # -------------------------
    # DATA PIPELINE
    # -------------------------
    terms = parse_csv(uploaded_file)

    landing_pages = (
        [x.strip() for x in landing_pages_raw.split("\n") if x.strip()]
        if campaign_type == "PMax"
        else None
    )

    with st.spinner("Layer 2 — Scraping landing pages..."):
        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )

    with st.spinner("Layer 3 — Building brand intelligence..."):
        brand_model_data = build_brand_model(
            page_text=landing_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )

    with st.spinner("Layer 4 — Prefiltering terms..."):
        auto_neg, remaining = contextual_prefilter(
            terms,
            brand_model_data
        )

    with st.spinner("Layer 5 — Classifying terms..."):
        negatives, reviews, positives = [], [], []

        for batch in chunk_list(remaining, 100):

            result = classify_terms_batch(
                model=model,
                batch_terms=batch,
                brand=brand_model_data,
                campaign_type=campaign_type,
                target_keywords=target_keywords,
                rules=CLASSIFICATION_RULES
            )

            negatives += result.get("negative", [])
            reviews += result.get("review", [])
            positives += result.get("positive", [])

        negatives += auto_neg

        layer5_data = {
            "negative": negatives,
            "review": reviews,
            "positive": positives
        }

    with st.spinner("Layer 6 — Extracting root negatives..."):
        roots = extract_roots_protected(
            negative_terms=layer5_data["negative"],
            review_terms=layer5_data["review"],
            positive_terms=layer5_data["positive"],
            brand_model=brand_model_data
        )

    with st.spinner("Layer 7 — Final formatting..."):
        final_data = final_classification(
            roots,
            brand_model_data
        )

    with st.spinner("Building outputs..."):
        outputs = build_outputs(
            brand_model=brand_model_data,
            layer5_data=layer5_data,
            layer6_roots=roots,
            layer7_data=final_data
        )

    # =====================================================
    # OUTPUT UI
    # =====================================================
    st.success("Analysis Complete")

    brand_clean = safe_flatten([outputs["brand_summary"]])

    brand_lines = []
    for item in brand_clean:
        if isinstance(item, str):
            # split multi-line strings into real lines
            brand_lines.extend(item.split("\n"))
        else:
            brand_lines.append(str(item))

    ui_box(
        "Brand Summary",
        text="\n".join([line for line in brand_lines if line.strip()])
    )
    
    review_clean = safe_flatten(outputs["review_queue"])
    ui_box("Review Queue", df=pd.DataFrame({"Review Terms": review_clean}))

    root_clean = safe_flatten(outputs["negatives_with_roots"])
    ui_box("Root Negatives", df=pd.DataFrame({"Root Negatives": root_clean}))

    ai_clean = safe_flatten(outputs["ai_variations"])
    ui_box("AI Variations", df=pd.DataFrame({"AI Variations": ai_clean}))

    ui_box(
        "Final Google Ads Negative List",
        text=outputs["final_google_ads"]
    )
