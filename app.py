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


# =====================================================
# MODEL
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")


# =====================================================
# PAGE CONFIG (Layer 1 - UI)
# =====================================================
st.set_page_config(page_title="Negative Keyworder V4", layout="wide")
st.title("Negative Keyworder V4")


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
# STATE OBJECT (CRITICAL FIX)
# =====================================================
state = {}


# =====================================================
# INPUTS (Layer 1)
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

target_keywords = st.text_area("Target Keywords (optional)", height=120)


# =====================================================
# RUN BUTTON
# =====================================================
if st.button("Run Analysis"):

    progress = st.progress(0)
    status = st.empty()

    # =================================================
    # VALIDATION (Layer 1 gatekeeping)
    # =================================================
    if not uploaded_file:
        st.error("E001 - Missing CSV file")
        st.stop()

    if campaign_type != "PMax" and not landing_page:
        st.error("E002 - Missing landing page URL")
        st.stop()

    if campaign_type == "PMax":
        landing_pages = [
            x.strip() for x in landing_pages_raw.split("\n") if x.strip()
        ]
        if not landing_pages:
            st.error("E003 - Missing PMax landing pages")
            st.stop()
    else:
        landing_pages = None


    # =================================================
    # STATE INITIALISATION
    # =================================================
    state["campaign_type"] = campaign_type
    state["terms"] = parse_csv(uploaded_file)
    state["landing_page"] = landing_page
    state["landing_pages"] = landing_pages
    state["target_keywords"] = target_keywords


    # =================================================
    # LAYER 2 — SCRAPER
    # =================================================
    status.info("Layer 2 - Scraping landing pages...")
    progress.progress(10)

    state["page_text"] = get_landing_context(
        campaign_type=campaign_type,
        landing_page=landing_page,
        landing_pages=landing_pages
    )


    # =================================================
    # LAYER 3 — BRAND INTELLIGENCE
    # =================================================
    status.info("Layer 3 - Building brand intelligence...")
    progress.progress(25)

    state["brand_model"] = build_brand_model(
        page_text=state["page_text"],
        target_keywords=target_keywords,
        campaign_type=campaign_type
    )


    # =================================================
    # LAYER 4 — PREFILTER (brand-driven ONLY)
    # =================================================
    status.info("Layer 4 - Prefiltering terms...")
    progress.progress(40)

    state["auto_negative"], state["remaining_terms"] = contextual_prefilter(
        state["terms"],
        state["brand_model"]
    )


    # =================================================
    # LAYER 5 — CLASSIFICATION (LLM)
    # =================================================
    status.info("Layer 5 - Classifying terms...")
    progress.progress(55)

    negatives, reviews, positives = [], [], []

    batches = list(chunk_list(state["remaining_terms"], 100))

    if not batches:
        st.warning("No terms left after prefilter")
        st.stop()

    for i, batch in enumerate(batches):

        status.info(f"Classifying batch {i+1}/{len(batches)}")

        result = classify_terms_batch(
            model=model,
            batch_terms=batch,
            brand=state["brand_model"],
            campaign_type=campaign_type,
            target_keywords=target_keywords
        )

        negatives += result.get("negative", [])
        reviews += result.get("review", [])
        positives += result.get("positive", [])

        progress.progress(55 + int((i + 1) / len(batches) * 20))


    state["classified"] = {
        "negative": negatives + state["auto_negative"],
        "review": reviews,
        "positive": positives
    }


    # =================================================
    # LAYER 6 — ROOT ENGINE
    # =================================================
    status.info("Layer 6 - Extracting roots...")
    progress.progress(80)

    state["roots"] = extract_roots_protected(
        negative_terms=state["classified"]["negative"],
        review_terms=state["classified"]["review"],
        positive_terms=state["classified"]["positive"],
        brand_model=state["brand_model"]
    )


    # =================================================
    # LAYER 7 — FINAL ENGINE
    # =================================================
    status.info("Layer 7 - Building final output...")
    progress.progress(90)

    state["final"] = final_classification(
        state["roots"],
        state["brand_model"]
    )

    state["outputs"] = build_outputs(
        state["final"],
        state["brand_model"]
    )


    # =================================================
    # DONE
    # =================================================
    progress.progress(100)
    status.success("Analysis complete")


    # =================================================
    # OUTPUT UI
    # =================================================
    st.subheader("1. Brand Summary")
    st.write(state["outputs"].get("brand_summary"))

    st.subheader("2. Review Queue")
    st.write(state["outputs"].get("review_queue"))

    st.subheader("3. Negatives (with confidence)")
    st.write(state["outputs"].get("negatives_with_confidence"))

    st.subheader("4. AI Variations")
    st.write(state["outputs"].get("ai_variations"))

    st.subheader("5. Final Google Ads Negative List")
    st.text_area(
        "Copy-paste ready",
        state["outputs"].get("final_google_ads"),
        height=300
    )

    st.subheader("6. Positive Keywords (hidden)")
    with st.expander("View"):
        st.write(state["outputs"].get("positives"))
