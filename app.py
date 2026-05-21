# =====================================================
# CORE LIBRARIES
# =====================================================
import streamlit as st
import pandas as pd
import google.generativeai as genai


# =====================================================
# PIPELINE MODULES (CORRECT ORDER)
# =====================================================
from scraper import get_landing_context
from context import build_context
from classify import classify_terms_batch
from postprocess import postprocess_results


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
# VALIDATION (NEW - REQUIRED)
# =====================================================
def validate_inputs():
    if not campaign_type:
        return "E100: Campaign type is required"

    if not uploaded_file:
        return "E101: Search terms CSV is required"

    if campaign_type == "PMax" and not landing_pages_raw:
        return "E102: Landing pages are required for PMax"

    if campaign_type in ["Display", "Shopping"] and not landing_page:
        return "E103: Landing page is required"

    if campaign_type == "Search" and (not landing_pages_raw or not target_keywords):
        return "E104: Search requires landing page + keywords"

    return None


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
- Default to NEGATIVE
- REVIEW only when unavoidable
- POSITIVE only when explicit buying intent exists
"""


# =====================================================
# UI INPUTS
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

if campaign_type == "Search":
    landing_pages_raw = st.text_area("Landing Page URL *")
    target_keywords = st.text_area("Target Keywords *")


# =====================================================
# STAGE 1 — BUILD CONTEXT
# =====================================================
if st.button("Build Brand Context"):

    clear_error()

    error = validate_inputs()
    if error:
        code, msg = error.split(": ", 1)
        set_error(code, msg)
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

    with st.expander("Brand Context (technical view)"):
        st.write(brand_model_data)


# =====================================================
# CONFIRM BUTTON (SAFE OUTSIDE FLOW)
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

    error = validate_inputs()
    if error:
        code, msg = error.split(": ", 1)
        set_error(code, msg)
        st.stop()

    if not st.session_state.brand_confirmed:
        set_error("E105", "Please confirm brand context first")
        st.stop()

    if not st.session_state.search_terms_cache or not st.session_state.brand_data:
        set_error("E106", "Missing pipeline state - rebuild brand context")
        st.stop()

    terms = st.session_state.search_terms_cache
    brand_model_data = st.session_state.brand_data

    # =====================================================
    # PIPELINE
    # =====================================================
    with st.spinner("Running full audit pipeline..."):

        auto_neg = []
        remaining = terms

        negatives, reviews, positives = [], [], []

        # CLASSIFICATION
        with st.spinner("Classifying search terms with AI..."):
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

        # POSTPROCESS
        with st.spinner("Generating final outputs..."):
            outputs = postprocess_results(
                layer5_data,
                brand_model_data
            )

    # =====================================================
    # OUTPUT UI (SAFE)
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
            "Roots": outputs.get("roots", [])
        }))

    with col3:
        st.subheader("AI Variations")
        st.dataframe(pd.DataFrame({
            "Variations": outputs.get("ai_negative_variations", [])
        }))

    st.divider()

    st.subheader("Final Google Ads Negative List")

    st.text_area(
        "Copy and paste directly into Google Ads",
        value=outputs.get("final_google_ads", ""),
        height=350
    )
