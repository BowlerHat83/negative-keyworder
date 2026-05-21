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
if "brand_data" not in st.session_state:
    st.session_state.brand_data = None

if "search_terms_cache" not in st.session_state:
    st.session_state.search_terms_cache = None

if "brand_confirmed" not in st.session_state:
    st.session_state.brand_confirmed = False


# =====================================================
# HELPERS
# =====================================================
def parse_csv(file):
    df = pd.read_csv(file)
    return df.iloc[:, 0].dropna().astype(str).tolist()


def chunk_list(data, size=100):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def format_brand_context(ctx: dict) -> str:
    if not ctx:
        return "No brand context available."

    def block(title, items):
        if not items:
            return "None"
        return "\n".join([f"- {x}" for x in items])

    return f"""
BRAND SUMMARY
=============

Positioning:
- {", ".join(ctx.get("positioning", [])) or "Unknown"}

Price Positioning:
- {", ".join(ctx.get("price_positioning", [])) or "Unknown"}

Intent Profile:
- Commercial: {ctx.get("intent_profile", {}).get("commercial", "unknown")}
- Informational: {ctx.get("intent_profile", {}).get("informational", "unknown")}
- Lead Generation: {ctx.get("intent_profile", {}).get("lead_generation", "unknown")}

Core Offerings:
{block("Core Offerings", ctx.get("core_offerings", []))}

Safe Roots:
{block("Safe Roots", ctx.get("safe_roots", []))}

Risk Terms:
{block("Risk Terms", ctx.get("risk_terms", []))}
"""


# =====================================================
# INPUTS (LIGHTWEIGHT STRUCTURED CONTEXT)
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

st.subheader("Brand Inputs (Optional but improves accuracy)")

brand_notes = st.text_area(
    "Brand Notes (what you sell, tone, pricing level, competitors)",
    height=100
)

price_hint = st.selectbox(
    "Price Positioning (optional)",
    ["Unknown", "Low", "Mid", "High", "Luxury"]
)

if campaign_type == "PMax":
    landing_pages_raw = st.text_area("Landing Pages (one per line) *")

elif campaign_type in ["Display", "Shopping"]:
    landing_page = st.text_input("Landing Page URL *")
    target_keywords = st.text_area("Target Keywords")

elif campaign_type == "Search":
    landing_pages_raw = st.text_area("Landing Page URL *")
    target_keywords = st.text_area("Target Keywords *")


# =====================================================
# MAIN ACTION (SINGLE BUTTON)
# =====================================================
if st.button("Confirm and Run Search Term Audit"):

    if not campaign_type or not uploaded_file:
        st.error("Campaign type and CSV are required")
        st.stop()

    terms = parse_csv(uploaded_file)
    st.session_state.search_terms_cache = terms

    landing_pages = (
        [x.strip() for x in landing_pages_raw.split("\n") if x.strip()]
        if landing_pages_raw else None
    )

    # =====================================================
    # SCRAPE
    # =====================================================
    with st.spinner("Scraping landing pages..."):
        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )

    # =====================================================
    # BRAND CONTEXT BUILD (NOW IMPROVED INPUTS INCLUDED)
    # =====================================================
    with st.spinner("Building brand context..."):

        enriched_prompt_context = f"""
Brand Notes:
{brand_notes}

Price Positioning Hint:
{price_hint}
"""

        brand_model_data = build_context(
            page_text=landing_context + "\n\n" + enriched_prompt_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )

    st.session_state.brand_data = brand_model_data
    st.session_state.brand_confirmed = True

    # =====================================================
    # DISPLAY CLEAN BRAND CONTEXT
    # =====================================================
    st.subheader("Brand Context (Auto-Generated)")

    st.text(format_brand_context(brand_model_data))

    # =====================================================
    # CLASSIFICATION
    # =====================================================
    negatives, reviews, positives = [], [], []

    with st.spinner("Classifying search terms..."):
        for batch in chunk_list(terms, 100):

            result = classify_terms_batch(
                model=model,
                batch_terms=batch,
                brand=brand_model_data,
                campaign_type=campaign_type,
                target_keywords=target_keywords,
                rules=""
            )

            negatives += result.get("negative", [])
            reviews += result.get("review", [])
            positives += result.get("positive", [])

    layer5_data = {
        "negative": negatives,
        "review": reviews,
        "positive": positives
    }

    # =====================================================
    # POSTPROCESS
    # =====================================================
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

    st.subheader("Review Queue")
    st.dataframe(pd.DataFrame({"Search Terms": outputs.get("review_queue", [])}))

    st.subheader("Root Signals")
    st.dataframe(pd.DataFrame({"Roots": outputs.get("negatives_with_roots", [])}))

    st.subheader("AI Variations")
    st.dataframe(pd.DataFrame({"Variations": outputs.get("ai_variations", [])}))

    st.subheader("Final Google Ads Negative List")
    st.text_area(
        "Copy into Google Ads",
        value=outputs.get("final_google_ads", ""),
        height=350
    )
