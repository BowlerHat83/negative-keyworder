import streamlit as st
import pandas as pd
import google.generativeai as genai

# =====================================================
# LAYERS
# =====================================================
from scraper import get_landing_context
from intelli import build_brand_model
from prefilter import contextual_prefilter
from classify import classify_terms_batch
from root import extract_roots_protected
from finalclass import final_classification
from output import build_outputs

# =====================================================
# GEMINI MODEL
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")

# =====================================================
# SESSION STATE ERROR HANDLING
# =====================================================
if "error" not in st.session_state:
    st.session_state.error = None

def set_error(code, msg):
    st.session_state.error = f"{code}: {msg}"

def clear_error():
    st.session_state.error = None

# =====================================================
# CSV PARSER
# =====================================================
def parse_csv(file):
    df = pd.read_csv(file)
    return df.iloc[:, 0].dropna().astype(str).tolist()

# =====================================================
# UI
# =====================================================
st.set_page_config(page_title="Negative Keyworder V4", layout="wide")
st.title("Negative Keyworder V4")

if st.session_state.error:
    st.error(st.session_state.error)

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

progress = st.progress(0)

# =====================================================
# RUN
# =====================================================
if st.button("Run Analysis"):

    clear_error()

    # -------------------------
    # VALIDATION
    # -------------------------
    if not uploaded_file:
        set_error("E001", "Missing search terms CSV")
        st.stop()

    if campaign_type != "PMax" and not landing_page:
        set_error("E002", "Missing landing page URL")
        st.stop()

    landing_pages = [
        x.strip() for x in landing_pages_raw.split("\n") if x.strip()
    ] if campaign_type == "PMax" else None

    # =====================================================
    # LAYER 2 — SCRAPER
    # =====================================================
    with st.spinner("Layer 2 — Scraping landing pages..."):
        progress.progress(10)

        landing_context = get_landing_context(
            campaign_type=campaign_type,
            landing_page=landing_page,
            landing_pages=landing_pages
        )

    # =====================================================
    # LAYER 3 — BRAND INTELLIGENCE
    # =====================================================
    with st.spinner("Layer 3 — Brand Intelligence..."):
        progress.progress(25)

        brand_model = build_brand_model(
            page_text=landing_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )

    # =====================================================
    # LAYER 4 — PREFILTER
    # =====================================================
    with st.spinner("Layer 4 — Prefilter..."):
        progress.progress(40)

        terms = parse_csv(uploaded_file)
        auto_neg, remaining = contextual_prefilter(terms, brand_model)

    # =====================================================
    # LAYER 5 — CLASSIFICATION
    # =====================================================
    with st.spinner("Layer 5 — Classification..."):
        progress.progress(55)

        negatives, reviews, positives = [], [], []

        batches = [remaining[i:i+100] for i in range(0, len(remaining), 100)]

        for i, batch in enumerate(batches):

            try:
                result = classify_terms_batch(
                    model=model,
                    batch_terms=batch,
                    brand=brand_model,
                    campaign_type=campaign_type,
                    target_keywords=target_keywords
                )

            except Exception as e:
                err = str(e)

                if "429" in err or "quota" in err.lower():
                    set_error("E429", "Gemini quota exceeded")
                else:
                    set_error("E500", "Classification error")

                st.stop()

            negatives += result.get("negative", [])
            reviews += result.get("review", [])
            positives += result.get("positive", [])

            progress.progress(55 + int((i + 1) / max(len(batches), 1) * 20))

        negatives += auto_neg

        layer5_data = {
            "negative": negatives,
            "review": reviews,
            "positive": positives
        }

    # =====================================================
    # LAYER 6 — ROOT EXTRACTION
    # =====================================================
    with st.spinner("Layer 6 — Root extraction..."):
        progress.progress(80)

        roots = extract_roots_protected(
            negative_terms=layer5_data["negative"],
            review_terms=layer5_data["review"],
            positive_terms=layer5_data["positive"],
            brand_model=brand_model
        )

    # =====================================================
    # LAYER 7 — FINAL CLASSIFICATION
    # =====================================================
    with st.spinner("Layer 7 — Final classification..."):
        progress.progress(90)

        final_data = final_classification(roots, brand_model)

    # =====================================================
    # LAYER 8 — OUTPUT
    # =====================================================
    with st.spinner("Layer 8 — Output generation..."):
        progress.progress(98)

        outputs = build_outputs(
            brand_model=brand_model,
            layer5_data=layer5_data,
            layer6_roots=roots,
            layer7_data=final_data
        )

    # =====================================================
    # COMPLETE
    # =====================================================
    progress.progress(100)
    st.success("Analysis complete")

    # =====================================================
    # OUTPUT UI
    # =====================================================
    st.subheader("1. Brand Summary")
    st.write(outputs["brand_summary"])

    st.subheader("2. Review Queue")
    st.write(outputs["review_queue"])

    st.subheader("3. Root Negatives")
    st.write(outputs["negatives_with_roots"])

    st.subheader("4. AI Variations")
    st.write(outputs["ai_variations"])

    st.subheader("5. Final Google Ads Negative List")
    st.text_area(
        "Copy-paste ready",
        outputs["final_google_ads"],
        height=300
    )
