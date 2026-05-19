import streamlit as st
import time

# =====================================================
# IMPORT LAYERS (your pipeline modules)
# =====================================================

try:
    from scraper import get_landing_context
    from classify import classify_terms_batch
    from prefilter import contextual_prefilter
    from intelli import contextual_prefilter
    from root import extract_roots
    from finalclass import final_classification
    from output import build_outputs
except Exception as e:
    st.error(f"Module import error: {e}")
    st.stop()

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="Negative Keyworder V4",
    layout="wide"
)

st.title("Negative Keyworder V4")

# =====================================================
# SESSION STATE (ERROR HANDLING)
# =====================================================

if "error" not in st.session_state:
    st.session_state.error = None

def set_error(msg):
    st.session_state.error = msg

def clear_error():
    st.session_state.error = None

if st.session_state.error:
    st.error(st.session_state.error)

# =====================================================
# UI INPUTS
# =====================================================

campaign_type = st.selectbox(
    "Campaign Type",
    ["Search", "Shopping", "Display", "PMax"]
)

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])

landing_page = None
landing_pages = None

if campaign_type == "PMax":
    landing_pages = st.text_area("Landing Pages (one per line)")
else:
    landing_page = st.text_input("Landing Page URL")

target_keywords = st.text_area("Target Keywords (Search only)", height=120)

# =====================================================
# PROGRESS UI
# =====================================================

progress = st.progress(0)
status = st.empty()

# =====================================================
# VALIDATION
# =====================================================

def validate():
    if not uploaded_file:
        set_error("Missing search terms CSV")
        return False

    if campaign_type != "PMax" and not landing_page:
        set_error("Missing landing page URL")
        return False

    if campaign_type == "PMax" and not landing_pages:
        set_error("Missing PMax landing pages")
        return False

    clear_error()
    return True

# =====================================================
# RUN BUTTON
# =====================================================

run = st.button("Run Analysis")

if run:

    if not validate():
        st.stop()

    # =================================================
    # STEP 1: LANDING PAGE SCRAPING
    # =================================================

    status.info("Scraping landing pages...")
    progress.progress(10)

    landing_context = get_landing_context(
        campaign_type=campaign_type,
        landing_page=landing_page,
        landing_pages=landing_pages
    )

    # =================================================
    # STEP 2: BRAND MODEL (LLM CONTEXT)
    # =================================================

    status.info("Building brand model...")
    progress.progress(30)

    brand_model = build_brand_model(
        page_text=landing_context,
        target_keywords=target_keywords,
        campaign_type=campaign_type
    )

    # =================================================
    # STEP 3: PREFILTER
    # =================================================

    status.info("Prefiltering terms...")
    progress.progress(50)

    prefiltered = run_prefilter(brand_model)

    # =================================================
    # STEP 4: ROOT EXTRACTION
    # =================================================

    status.info("Extracting root negatives...")
    progress.progress(65)

    roots = extract_roots(prefiltered, brand_model)

    # =================================================
    # STEP 5: FINAL CLASSIFICATION
    # =================================================

    status.info("Final classification...")
    progress.progress(80)

    final_data = final_classification(roots, brand_model)

    # =================================================
    # STEP 6: OUTPUT GENERATION
    # =================================================

    status.info("Generating outputs...")
    progress.progress(95)

    outputs = build_outputs(final_data, brand_model)

    # =================================================
    # DONE
    # =================================================

    progress.progress(100)
    status.success("Analysis complete")

    # =================================================
    # OUTPUT DISPLAY (6 OUTPUT STRUCTURE)
    # =================================================

    st.subheader("1. Brand Summary")
    st.write(outputs.get("brand_summary"))

    st.subheader("2. Review Queue")
    st.write(outputs.get("review_queue"))

    st.subheader("3. Search Term Negatives (with confidence)")
    st.write(outputs.get("negatives_with_confidence"))

    st.subheader("4. AI Generated Variations")
    st.write(outputs.get("ai_variations"))

    st.subheader("5. Final Google Ads Negative List")
    st.text_area(
        "Copy-paste ready",
        outputs.get("final_google_ads"),
        height=300
    )

    st.subheader("6. Positive Keywords (hidden logic)")
    with st.expander("View hidden positives"):
        st.write(outputs.get("positives"))
