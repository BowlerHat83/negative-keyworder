# =====================================================
# CORE LIBRARIES
# =====================================================
import streamlit as st
import pandas as pd
import google.generativeai as genai

# =====================================================
# PIPELINE MODULES (CLEAN ARCHITECTURE)
# =====================================================
from scraper import get_landing_context
from context import build_context
from classify import classify_terms_batch
from postprocess import (
    extract_roots_protected,
    final_classification,
    build_outputs
)

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
# SESSION STATE
# =====================================================
if "error" not in st.session_state:
    st.session_state.error = None

if "brand_confirmed" not in st.session_state:
    st.session_state.brand_confirmed = False

if "brand_data" not in st.session_state:
    st.session_state.brand_data = None

if "search_terms_cache" not in st.session_state:
    st.session_state.search_terms_cache = None


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
    return df.iloc[:, 0].dropna().astype(str).tolist()


def chunk_list(data, size=100):
    for i in range(0, len(data), size):
        yield data[i:i + size]


# =====================================================
# CLASSIFICATION RULES
# =====================================================
CLASSIFICATION_RULES = """
You are a strict PPC search term classifier.

Return JSON only:
{
  "negative": [],
  "review": [],
  "positive": []
}

Rules:
- REVIEW only when unavoidable ambiguity exists
- POSITIVE only when clear buying intent exists
"""

# =====================================================
# INPUTS
# =====================================================
campaign_type = st.selectbox(
    "Campaign Type *",
    ["", "Search", "Shopping", "Display", "PMax"]
)

uploaded_file = st.file_uploader(
    "Search Terms CSV *",
    type=["csv"]
)

landing_page = None
landing_pages_raw = None
target_keywords = None

if campaign_type == "PMax":
    landing_pages_raw = st.text_area("Landing Pages (one per line) *")

elif campaign_type in ["Display", "Shopping"]:
    landing_page = st.text_input("Landing Page URL *")
    target_keywords = st.text_area("Target Keywords")

elif campaign_type == "Search":
    landing_pages_raw = st.text_area("Landing Page URL *")
    target_keywords = st.text_area("Target Keywords *")

# =====================================================
# STAGE 1 — BUILD CONTEXT
# =====================================================
if st.button("Build Brand Context"):

    clear_error()

    if not campaign_type:
        set_error("E100", "Campaign type required")
        st.stop()

    if not uploaded_file:
        set_error("E101", "Search terms CSV required")
        st.stop()

    if campaign_type == "PMax" and not landing_pages_raw:
        set_error("E102", "Landing pages required for PMax")
        st.stop()

    if campaign_type in ["Display", "Shopping"] and not landing_page:
        set_error("E103", "Landing page required")
        st.stop()

    if campaign_type == "Search" and (not landing_pages_raw or not target_keywords):
        set_error("E104", "Search requires landing page + keywords")
        st.stop()

    terms = parse_csv(uploaded_file)
    st.session_state.search_terms_cache = terms

    landing_pages = (
        [x.strip() for x in landing_pages_raw.split("\n") if x.strip()]
        if campaign_type == "PMax"
        else None
    )

    with st.spinner("Scraping landing pages..."):
        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )

    with st.spinner("Building brand context..."):
        brand_model_data = build_context(
            page_text=landing_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )

    st.session_state.brand_data = brand_model_data

    with st.expander("Brand Context"):
        st.write(brand_model_data)

# =====================================================
# CONFIRM BRAND
# =====================================================
if st.session_state.brand_data and not st.session_state.brand_confirmed:
    if st.button("Confirm Brand Context"):
        st.session_state.brand_confirmed = True
        st.success("Brand confirmed. You can now run audit.")

# =====================================================
# STAGE 2 — RUN AUDIT
# =====================================================
if st.button("Run Search Term Audit"):

    clear_error()

    if not st.session_state.brand_confirmed:
        set_error("E105", "Please confirm brand context first")
        st.stop()

    if not st.session_state.search_terms_cache or not st.session_state.brand_data:
        set_error("E106", "Missing brand context or search terms")
        st.stop()

    terms = st.session_state.search_terms_cache
    brand_model_data = st.session_state.brand_data

    # =====================================================
    # PIPELINE EXECUTION
    # =====================================================
    with st.spinner("Running full audit pipeline..."):

        negatives, reviews, positives = [], [], []

        with st.spinner("Classifying search terms..."):
            for batch in chunk_list(terms, 100):

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

        layer5_data = {
            "negative": negatives,
            "review": reviews,
            "positive": positives
        }

        # =================================================
        # POSTPROCESS PIPELINE (FIXED)
        # =================================================

        roots = extract_roots_protected(
            negative_terms=layer5_data["negative"],
            review_terms=layer5_data["review"],
            positive_terms=layer5_data["positive"],
            brand_model=brand_model_data
        )

        final_data = final_classification(
            roots=roots,
            brand_model=brand_model_data
        )

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

    with st.expander("Brand Summary"):
        st.write(outputs.get("brand_summary", {}))

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Review Queue")
        st.dataframe(pd.DataFrame({
            "Search Terms": outputs.get("review_queue", [])
        }))

    with col2:
        st.subheader("Root Signals")
        st.dataframe(pd.DataFrame({
            "Roots": outputs.get("negatives_with_roots", [])
        }))

    with col3:
        st.subheader("AI Variations")
        st.dataframe(pd.DataFrame({
            "Variations": outputs.get("ai_variations", [])
        }))

    st.divider()

    st.subheader("Final Google Ads Negative List")

    st.text_area(
        "Copy and paste directly into Google Ads",
        value=outputs.get("final_google_ads", ""),
        height=350
    )
