import streamlit as st
import pandas as pd
import google.generativeai as genai

from scraper import get_landing_context
from intelli import build_brand_model
from prefilter import contextual_prefilter
from classify import classify_terms_batch
from root import extract_roots_protected
from finalclass import final_classification
from output import build_outputs


# =========================
# MODEL
# =========================
model = genai.GenerativeModel("gemini-2.5-flash")


# =========================
# ERROR HANDLER
# =========================
def error(code, msg):
    st.error(f"[{code}] {msg}")


# =========================
# CSV PARSER
# =========================
def parse_csv(file):
    try:
        df = pd.read_csv(file)
        return df.iloc[:, 0].dropna().astype(str).tolist()
    except Exception:
        return None


# =========================
# CHUNKING
# =========================
def chunk(data, size=100):
    for i in range(0, len(data), size):
        yield data[i:i+size]


# =========================
# UI CONFIG
# =========================
st.set_page_config(page_title="Negative Keyworder V4", layout="wide")
st.title("Negative Keyworder V4")


# =========================
# INPUTS (ADAPTIVE UI HOOK READY)
# =========================
campaign_type = st.selectbox("Campaign Type", ["Search", "Shopping", "Display", "PMax"])

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])

landing_page = None
landing_pages = None

if campaign_type == "PMax":
    landing_pages = st.text_area("Landing Pages (one per line)")
else:
    landing_page = st.text_input("Landing Page URL")

target_keywords = st.text_area("Target Keywords (optional)")


# =========================
# RUN BUTTON
# =========================
if st.button("Run Analysis"):

    # -------------------------
    # VALIDATION GATE (CRITICAL)
    # -------------------------
    if not campaign_type:
        error("E401", "Campaign type not selected")
        st.stop()

    if not uploaded_file:
        error("E401", "Missing CSV file")
        st.stop()

    if campaign_type != "PMax" and not landing_page:
        error("E403", "Missing landing page URL")
        st.stop()

    if campaign_type == "PMax" and not landing_pages:
        error("E403", "Missing PMax landing pages")
        st.stop()

    # -------------------------
    # STEP 1 - LOAD TERMS
    # -------------------------
    with st.spinner("Loading search terms..."):
        terms = parse_csv(uploaded_file)

    if not terms:
        error("E402", "CSV is empty or invalid")
        st.stop()

    progress = st.progress(0)
    status = st.empty()

    # -------------------------
    # STEP 2 - LANDING CONTEXT
    # -------------------------
    status.info("Step 1/6: Scraping landing page")
    landing_context = get_landing_context(
        campaign_type=campaign_type,
        landing_page=landing_page,
        landing_pages=landing_pages
    )
    progress.progress(15)

    # -------------------------
    # STEP 3 - BRAND MODEL
    # -------------------------
    status.info("Step 2/6: Building brand model")
    brand_model = build_brand_model(
        page_text=landing_context,
        target_keywords=target_keywords,
        campaign_type=campaign_type
    )
    progress.progress(30)

    # -------------------------
    # STEP 4 - PREFILTER
    # -------------------------
    status.info("Step 3/6: Prefiltering terms")

    auto_neg, remaining = contextual_prefilter(terms, brand_model)

    if not remaining and not auto_neg:
        error("E404", "No usable terms after prefilter")
        st.stop()

    progress.progress(45)

    # -------------------------
    # STEP 5 - CLASSIFICATION
    # -------------------------
    status.info("Step 4/6: AI classification")

    classified = {"negative": [], "review": [], "positive": []}

    try:
        for batch in chunk(remaining, 100):

            result = classify_terms_batch(
                model=model,
                batch_terms=batch,
                brand=brand_model,
                campaign_type=campaign_type,
                target_keywords=target_keywords
            )

            classified["negative"] += result.get("negative", [])
            classified["review"] += result.get("review", [])
            classified["positive"] += result.get("positive", [])

        classified["negative"] += auto_neg

    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e):
            error("E429", "Gemini quota exceeded")
        else:
            error("E500", str(e))
        st.stop()

    progress.progress(70)

    # -------------------------
    # STEP 6 - ROOTS
    # -------------------------
    status.info("Step 5/6: Extracting roots")

    roots = extract_roots_protected(
        negative_terms=classified["negative"],
        review_terms=classified["review"],
        positive_terms=classified["positive"],
        brand_model=brand_model
    )

    progress.progress(85)

    # -------------------------
    # STEP 7 - FINAL
    # -------------------------
    status.info("Step 6/6: Final processing")

    final_data = final_classification(
        roots=roots,
        classified=classified,
        brand_model=brand_model
    )

    outputs = build_outputs(final_data, brand_model)

    progress.progress(100)
    status.success("Complete")

    # -------------------------
    # OUTPUT UI
    # -------------------------
    st.subheader("Brand Summary")
    st.write(outputs.get("brand_summary"))

    st.subheader("Review Queue")
    st.write(outputs.get("review_queue"))

    st.subheader("Negatives")
    st.write(outputs.get("negatives_with_confidence"))

    st.subheader("Final List")
    st.text_area("Copy", outputs.get("final_google_ads"), height=300)

    st.subheader("Positives (hidden)")
    with st.expander("View"):
        st.write(outputs.get("positives"))
