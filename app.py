import streamlit as st
import pandas as pd
import google.generativeai as genai

from scraper import get_landing_context
from classify import classify_terms_batch
from prefilter import contextual_prefilter
from intelli import build_brand_model
from root import extract_roots_protected
from finalclass import final_classification
from output import build_outputs


# =====================================================
# MODEL
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")


# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="Negative Keyworder V4", layout="wide")
st.title("Negative Keyworder V4")


# =====================================================
# CSV PARSER
# =====================================================
def parse_csv(file):
    df = pd.read_csv(file)
    return df.iloc[:, 0].dropna().astype(str).tolist()


# =====================================================
# CHUNKING
# =====================================================
def chunk_list(data, size=100):
    for i in range(0, len(data), size):
        yield data[i:i + size]


# =====================================================
# INPUTS
# =====================================================
campaign_type = st.selectbox(
    "Campaign Type",
    ["Search", "Shopping", "Display", "PMax"]
)

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])

landing_page = st.text_input("Landing Page URL")

landing_pages_raw = ""
if campaign_type == "PMax":
    landing_pages_raw = st.text_area("Landing Pages (one per line)")

target_keywords = st.text_area("Target Keywords (optional)")


# =====================================================
# RUN BUTTON
# =====================================================
if st.button("Run Analysis"):

    # -------------------------
    # VALIDATION
    # -------------------------
    if not uploaded_file:
        st.error("Upload a CSV file")
        st.stop()

    if campaign_type != "PMax" and not landing_page:
        st.error("Landing page required")
        st.stop()

    landing_pages = None
    if campaign_type == "PMax":
        landing_pages = [
            x.strip() for x in landing_pages_raw.split("\n") if x.strip()
        ]

    # -------------------------
    # STEP 1: LOAD TERMS
    # -------------------------
    terms = parse_csv(uploaded_file)

    # -------------------------
    # STEP 2: LANDING CONTEXT
    # -------------------------
    landing_context = get_landing_context(
        campaign_type=campaign_type,
        landing_page=landing_page,
        landing_pages=landing_pages
    )

    # -------------------------
    # STEP 3: BRAND MODEL
    # -------------------------
    brand_model = build_brand_model(
        page_text=landing_context,
        target_keywords=target_keywords,
        campaign_type=campaign_type
    )

    # -------------------------
    # STEP 4: PREFILTER
    # -------------------------
    auto_neg, remaining = contextual_prefilter(terms, brand_model)

    # -------------------------
    # STEP 5: CLASSIFY
    # -------------------------
    negatives, reviews, positives = [], [], []

    batches = list(chunk_list(remaining, 100))
    progress = st.progress(0)
    status = st.empty()

    if len(batches) == 0:
        st.warning("No terms after prefilter")
        st.stop()

    for i, batch in enumerate(batches):

        status.info(f"Processing batch {i+1}/{len(batches)}")

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

        progress.progress(int((i + 1) / len(batches) * 60))

    # include deterministic negatives
    negatives += auto_neg

    classified = {
        "negative": negatives,
        "review": reviews,
        "positive": positives
    }

    # -------------------------
    # STEP 6: ROOT EXTRACTION
    # -------------------------
    roots = extract_roots_protected(
        negative_terms=classified["negative"],
        review_terms=classified["review"],
        positive_terms=classified["positive"],
        brand_model=brand_model
    )

    # -------------------------
    # STEP 7: FINAL CLASSIFICATION
    # -------------------------
    final_data = final_classification(roots, brand_model)

    # -------------------------
    # STEP 8: OUTPUTS
    # -------------------------
    outputs = build_outputs(final_data, brand_model)

    progress.progress(100)
    status.success("Analysis complete")

    # -------------------------
    # UI OUTPUTS
    # -------------------------
    st.subheader("1. Brand Summary")
    st.write(outputs.get("brand_summary"))

    st.subheader("2. Review Queue")
    st.write(outputs.get("review_queue"))

    st.subheader("3. Negatives (with confidence)")
    st.write(outputs.get("negatives_with_confidence"))

    st.subheader("4. AI Variations")
    st.write(outputs.get("ai_variations"))

    st.subheader("5. Final Google Ads Negative List")
    st.text_area(
        "Copy-paste ready",
        outputs.get("final_google_ads"),
        height=300
    )

    st.subheader("6. Positive Keywords (hidden)")
    with st.expander("View"):
        st.write(outputs.get("positives"))
