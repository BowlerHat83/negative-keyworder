# =====================================================
# CORE LIBRARIES
# =====================================================
import streamlit as st
import pandas as pd
import google.generativeai as genai

# =====================================================
# PIPELINE MODULES
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
    page_title="Negative Keyworder",
    layout="wide"
)

st.title("Negative Keyworder")

# =====================================================
# SESSION STATE
# =====================================================
if "error" not in st.session_state:
    st.session_state.error = None

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
Return JSON only:
{
  "negative": [],
  "review": [],
  "positive": []
}
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
# BRAND CONTEXT FORMATTER (USER FRIENDLY FIXED)
# =====================================================
def format_brand_context(ctx: dict) -> str:
    if not ctx:
        return "⚠️ No brand context generated."

    def list_block(title, items):
        items = items or []
        if len(items) == 0:
            return f"### {title}\n- None"
        return f"### {title}\n" + "\n".join(f"- {x}" for x in items)

    intent = ctx.get("intent_profile") or {}

    return f"""
## Brand Summary

### Positioning
- {", ".join(ctx.get("positioning", ["Unknown"]))}

### Core Offerings
{list_block("Core Offerings", ctx.get("core_offerings", []))}

### Price Positioning
- {", ".join(ctx.get("price_positioning", ["Unknown"]))}

### Intent Profile
- Commercial: {intent.get("commercial", "unknown")}
- Informational: {intent.get("informational", "unknown")}
- Lead Gen: {intent.get("lead_generation", "unknown")}

### Safe Roots
{list_block("Safe Roots", ctx.get("safe_roots", []))}

### Risk Terms
{list_block("Risk Terms", ctx.get("risk_terms", []))}
"""


# =====================================================
# MAIN ACTION
# =====================================================
if st.button("Build & Run Audit"):

    clear_error()

    # -------------------------
    # VALIDATION
    # -------------------------
    if not campaign_type:
        set_error("E100", "Campaign type required")
        st.stop()

    if not uploaded_file:
        set_error("E101", "Search terms CSV required")
        st.stop()

    terms = parse_csv(uploaded_file)
    st.session_state.search_terms_cache = terms

    # -------------------------
    # LANDING CONTEXT (SAFE)
    # -------------------------
    landing_pages = None
    if landing_pages_raw:
        landing_pages = [x.strip() for x in landing_pages_raw.split("\n") if x.strip()]

    with st.spinner("Scraping landing pages..."):
        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )

    if not landing_context:
        landing_context = "No landing page content could be extracted."

    # -------------------------
    # BRAND CONTEXT (IMPROVED STABILITY)
    # -------------------------
    with st.spinner("Building brand context..."):
        brand_model_data = build_context(
            page_text=landing_context,
            target_keywords=target_keywords or "",
            campaign_type=campaign_type
        )

    st.session_state.brand_data = brand_model_data

    st.subheader("Brand Context")
    st.markdown(format_brand_context(brand_model_data))

    # -------------------------
    # CLASSIFICATION
    # -------------------------
    negatives, reviews, positives = [], [], []

    with st.spinner("Classifying search terms..."):
        for batch in chunk_list(terms, 100):

            result = classify_terms_batch(
                model=model,
                batch_terms=batch,
                brand=brand_model_data,
                campaign_type=campaign_type,
                target_keywords=target_keywords or "",
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

    # -------------------------
    # ROOTS + EXPANSION
    # -------------------------
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

    # -------------------------
    # OUTPUT
    # -------------------------
    st.success("Analysis Complete")

    with st.expander("Brand Summary (Expanded)"):
        st.markdown(format_brand_context(brand_model_data))

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
        "Copy into Google Ads",
        value=outputs.get("final_google_ads", ""),
        height=350
    )
