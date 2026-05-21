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
    return (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .tolist()
    )


def chunk_list(data, size=100):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def safe_flatten(lst):
    clean = []
    for item in lst:
        if isinstance(item, list):
            clean.extend(item)
        elif item is None:
            continue
        else:
            clean.append(item)
    return clean


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
    "Campaign Type",
    ["", "Search", "Shopping", "Display", "PMax"]
)

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])

landing_page = None
landing_pages_raw = None
target_keywords = None


if campaign_type == "PMax":
    landing_pages_raw = st.text_area("Landing Pages (one per line)")

elif campaign_type in ["Display", "Shopping"]:
    landing_page = st.text_input("Landing Page URL")
    target_keywords = st.text_area("Target Keywords (optional for non-Search)")

if campaign_type == "Search":
    landing_pages_raw = st.text_area("Landing Page URL")
    target_keywords = st.text_area("Target Keywords")

# =====================================================
# STAGE 1 — BUILD BRAND CONTEXT
# =====================================================
build_brand = st.button("Build Brand Context")

if build_brand:

    clear_error()

    if not uploaded_file:
        set_error("E001", "Missing CSV")
        st.stop()

    if not landing_page and not landing_pages_raw:
        set_error("E002", "Missing landing page(s)")
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
        brand_model_data = build_brand_model(
            page_text=landing_context,
            target_keywords=target_keywords,
            campaign_type=campaign_type
        )

    st.session_state.brand_data = brand_model_data

    st.subheader("Brand Context Review")
    st.json(brand_model_data)

    if st.button("Confirm Brand Context"):
        st.session_state.brand_confirmed = True
        st.success("Brand confirmed. You can now run audit.")


# =====================================================
# STAGE 2 — RUN AUDIT (ONLY AFTER CONFIRMATION)
# =====================================================
run_analysis = st.button(
    "Run Search Term Audit",
    disabled=not st.session_state.brand_confirmed
)

if run_analysis and st.session_state.brand_confirmed:

    clear_error()

    terms = st.session_state.search_terms_cache
    brand_model_data = st.session_state.brand_data

    # -------------------------
    # PREFILTER
    # -------------------------
    auto_neg, remaining = contextual_prefilter(
        terms,
        brand_model_data
    )

    # -------------------------
    # CLASSIFICATION
    # -------------------------
    negatives, reviews, positives = [], [], []

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

    # -------------------------
    # ROOTS
    # -------------------------
    roots = extract_roots_protected(
        negative_terms=layer5_data["negative"],
        review_terms=layer5_data["review"],
        positive_terms=layer5_data["positive"],
        brand_model=brand_model_data
    )

    # -------------------------
    # FINAL FORMAT
    # -------------------------
    final_data = final_classification(
        roots,
        brand_model_data
    )

    # -------------------------
    # OUTPUTS
    # -------------------------
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

    brand_clean = safe_flatten([outputs["brand_summary"]])
    st.subheader("Brand Summary")
    st.text("\n".join(map(str, brand_clean)))

    st.subheader("Review Queue")
    st.dataframe(pd.DataFrame({"Review Terms": reviews}))

    st.subheader("Root Negatives")
    st.dataframe(pd.DataFrame({"Root Negatives": roots}))

    st.subheader("AI Variations")
    st.dataframe(pd.DataFrame({"AI Variations": outputs["ai_variations"]}))

    st.subheader("Final Google Ads Negative List")
    st.text_area("Copy Paste", outputs["final_google_ads"], height=300)
