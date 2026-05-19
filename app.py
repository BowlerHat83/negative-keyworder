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
st.set_page_config(page_title="Final Version", layout="wide")
st.title("Negative Keyworder - Final Version")


# =====================================================
# SESSION ERROR
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
    return df.iloc[:, 0].dropna().astype(str).tolist()


def chunk_list(data, size=100):
    for i in range(0, len(data), size):
        yield data[i:i + size]


# =====================================================
# UI STATE MACHINE (THIS IS THE FIX)
# =====================================================
campaign_type = st.selectbox(
    "Campaign Type",
    ["", "Search", "Shopping", "Display", "PMax"]
)

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])

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

    landing_page = st.text_input("Landing Page URL")

    target_keywords = st.text_area(
        "Optional Keywords (used in brand model)"
    )

# =====================================================
# 🔴 SEARCH MODE (STRICT)
# =====================================================
elif campaign_type == "Search":

    landing_page = st.text_input("Landing Page URL")

    target_keywords = st.text_area(
        "Target Keywords (REQUIRED)"
    )


run = st.button("Run Analysis")


# =====================================================
# RUN PIPELINE
# =====================================================
if run:

    clear_error()

    # -------------------------
    # VALIDATION GATE
    # -------------------------
    if not uploaded_file:
        set_error("E001", "Missing search terms CSV")
        st.stop()

    if campaign_type == "":
        set_error("E000", "Please select a valid campaign type")
        st.stop()

    if campaign_type == "PMax":
        if not landing_pages_raw:
            set_error("E002", "PMax requires landing pages (one per line)")
            st.stop()

    else:
        if not landing_page:
            set_error("E003", "Missing landing page URL")
            st.stop()

    if campaign_type == "Search" and not target_keywords:
        set_error("E004", "Search campaigns require target keywords")
        st.stop()


    # -------------------------
    # PARSE INPUTS
    # -------------------------
    terms = parse_csv(uploaded_file)

    landing_pages = (
        [x.strip() for x in landing_pages_raw.split("\n") if x.strip()]
        if campaign_type == "PMax"
        else None
    )


    # =====================================================
    # LAYER 2 — SCRAPER
    # =====================================================
    with st.spinner("Scraping landing pages..."):

        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )


    # =====================================================
    # LAYER 3 — BRAND INTELLIGENCE
    # =====================================================
    with st.spinner("Building brand intelligence..."):

        brand_model = build_brand_model(
            page_text=landing_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )


    # =====================================================
    # LAYER 4 — PREFILTER
    # =====================================================
    with st.spinner("Prefiltering terms..."):

        auto_neg, remaining = contextual_prefilter(terms, brand_model)


    # =====================================================
    # LAYER 5 — CLASSIFICATION
    # =====================================================
    with st.spinner("Classifying terms..."):

        negatives, reviews, positives = [], [], []

        batches = list(chunk_list(remaining, 100))

        for batch in batches:

            result = classify_terms_batch(
                model=model,
                batch_terms=batch,
                brand=brand_model,
                campaign_type=campaign_type,
                target_keywords=target_keywords
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
    # LAYER 6 — ROOTS
    # =====================================================
    with st.spinner("Extracting root negatives..."):

        roots = extract_roots_protected(
            negative_terms=layer5_data["negative"],
            review_terms=layer5_data["review"],
            positive_terms=layer5_data["positive"],
            brand_model=brand_model
        )


    # =====================================================
    # LAYER 7 — FINAL CLASSIFICATION
    # =====================================================
    with st.spinner("Final classification..."):

        final_data = final_classification(roots, brand_model)


    # =====================================================
    # LAYER 8 — OUTPUT
    # =====================================================
    with st.spinner("Building outputs..."):

        outputs = build_outputs(
            brand_model=brand_model,
            layer5_data=layer5_data,
            layer6_roots=roots,
            layer7_data=final_data
        )


    # =====================================================
    # DONE
    # =====================================================
    st.success("Analysis complete")


    # =====================================================
    # OUTPUT UI
    # =====================================================
    st.subheader("Brand Summary")
    st.write(outputs["brand_summary"])

    st.subheader("Review Queue")
    st.write(outputs["review_queue"])

    st.subheader("Root Negatives")
    st.write(outputs["negatives_with_roots"])

    st.subheader("AI Variations")
    st.write(outputs["ai_variations"])

    st.subheader("Final Google Ads Negative List")
    st.text_area(
        "Copy-paste ready",
        outputs["final_google_ads"],
        height=300
    )
