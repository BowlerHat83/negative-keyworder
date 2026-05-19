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


# =====================================================
# CLASSIFICATION RULES (UPDATED DROP-IN)
# =====================================================
CLASSIFICATION_RULES = """
You are a strict PPC search term classifier.

=====================================================
HARD OUTPUT BIAS (CRITICAL)
=====================================================

You MUST strongly prefer NEGATIVE classification.

Decision hierarchy:
1. NEGATIVE (default)
2. POSITIVE (only when clearly high intent)
3. REVIEW (EXTREMELY rare)

IMPORTANT:
- REVIEW is DISCOURAGED unless absolutely necessary
- If you are unsure → choose NEGATIVE
- Do NOT use REVIEW as a safe option

=====================================================
REVIEW PENALTY RULE
=====================================================

You MUST NOT overuse REVIEW.

Only use REVIEW if ALL conditions are met:
- The term is clearly commercial-adjacent
AND
- Misclassifying it as negative would likely remove meaningful revenue
AND
- You cannot confidently label it positive or negative

If ANY condition is missing → choose NEGATIVE.

=====================================================
NEGATIVE DEFINITION (EXPANDED DEFAULT)
=====================================================

NEGATIVE includes:
- informational intent
- research intent
- comparison intent
- jobs / careers
- DIY / how-to
- low purchase intent
- vague intent
- competitor research
- unrelated traffic

DEFAULT ACTION:
→ NEGATIVE

=====================================================
POSITIVE DEFINITION (STRICT)
=====================================================

POSITIVE only if:
- clear buying intent
- product/service explicitly desired
- strong commercial relevance
- high likelihood of conversion

If not clearly positive → DO NOT mark positive

=====================================================
OUTPUT REQUIREMENTS
=====================================================

- Every term must be classified
- No explanations
- No missing terms
- JSON only

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

    if campaign_type == "PMax":
        if not landing_pages_raw:
            set_error("E002", "PMax requires landing pages")
            st.stop()

    else:
        if not landing_page:
            set_error("E003", "Missing landing page URL")
            st.stop()

    if campaign_type == "Search" and not target_keywords:
        set_error("E004", "Search campaigns require target keywords")
        st.stop()

    terms = parse_csv(uploaded_file)

    landing_pages = (
        [x.strip() for x in landing_pages_raw.split("\n") if x.strip()]
        if campaign_type == "PMax"
        else None
    )

    # =====================================================
    # LAYER 2 — SCRAPER
    # =====================================================
    with st.spinner("Layer 2 — Scraping landing pages..."):

        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )

    # =====================================================
    # LAYER 3 — BRAND INTELLIGENCE
    # =====================================================
    with st.spinner("Layer 3 — Building brand intelligence..."):

        brand_model_data = build_brand_model(
            page_text=landing_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )

    # =====================================================
    # LAYER 4 — PREFILTER
    # =====================================================
    with st.spinner("Layer 4 — Prefiltering terms..."):

        auto_neg, remaining = contextual_prefilter(
            terms,
            brand_model_data
        )

    # =====================================================
    # LAYER 5 — CLASSIFICATION ENGINE
    # =====================================================
    with st.spinner("Layer 5 — Classifying terms..."):

        negatives = []
        reviews = []
        positives = []

        batches = list(chunk_list(remaining, 100))

        for batch in batches:

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

    # =====================================================
    # LAYER 6 — ROOT EXTRACTION
    # =====================================================
    with st.spinner("Layer 6 — Extracting root negatives..."):

        roots = extract_roots_protected(
            negative_terms=layer5_data["negative"],
            review_terms=layer5_data["review"],
            positive_terms=layer5_data["positive"],
            brand_model=brand_model_data
        )

    # =====================================================
    # LAYER 7 — FINAL FORMATTING
    # =====================================================
    with st.spinner("Layer 7 — Final formatting..."):

        final_data = final_classification(
            roots,
            brand_model_data
        )

    # =====================================================
    # LAYER 8 — OUTPUT BUILDER
    # =====================================================
    with st.spinner("Layer 8 — Building outputs..."):

        outputs = build_outputs(
            brand_model=brand_model_data,
            layer5_data=layer5_data,
            layer6_roots=roots,
            layer7_data=final_data
        )

    st.success("Analysis Complete")

    # =====================================================
    # OUTPUTS
    # =====================================================
    st.subheader("Review Queue")
    st.write(outputs["review_queue"])

    st.subheader("Root Negatives")
    st.write(outputs["negatives_with_roots"])

    st.subheader("Final Output")
    st.text_area(
        "Copy-paste ready",
        outputs["final_google_ads"],
        height=300
    )
