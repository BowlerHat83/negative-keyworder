import streamlit as st
import pandas as pd

# =========================
# CONFIG
# =========================

st.set_page_config("Negative Keyworder V4", layout="wide")
st.title("Negative Keyworder V4")

# =========================
# STATE
# =========================

if "error_code" not in st.session_state:
    st.session_state.error_code = None

def set_error(code, msg):
    st.session_state.error_code = (code, msg)

def clear_error():
    st.session_state.error_code = None

# =========================
# INPUTS
# =========================

campaign_type = st.selectbox(
    "Campaign Type",
    ["Search", "Shopping", "PMax", "Display"]
)

uploaded_file = st.file_uploader("Search Terms CSV", type=["csv"])

search_terms = ""

if uploaded_file:
    df = pd.read_csv(uploaded_file, engine="python")
    col = st.selectbox("Column", df.columns)

    search_terms = "\n".join(df[col].dropna().astype(str))

landing_page = None
landing_pages = None

if campaign_type == "PMax":
    landing_pages = st.text_area("Landing Pages (one per line)")
else:
    landing_page = st.text_input("Landing Page URL")

target_keywords = st.text_area("Target Keywords")

# =========================
# VALIDATION
# =========================

def validate():
    if not uploaded_file:
        set_error("E001", "Missing CSV")
        return False

    if not search_terms.strip():
        set_error("E002", "Empty search terms")
        return False

    if campaign_type == "PMax" and not landing_pages:
        set_error("E003", "Missing PMax URLs")
        return False

    if campaign_type != "PMax" and not landing_page:
        set_error("E003", "Missing landing page")
        return False

    if campaign_type == "Search" and not target_keywords.strip():
        set_error("E004", "Missing keywords")
        return False

    clear_error()
    return True

# =========================
# RUN BUTTON
# =========================

run = st.button("Analyse")

if run:
    if not validate():
        st.stop()

    st.success("Validated — pipeline starting...")
