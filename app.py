import streamlit as st
import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# Load model
model = genai.GenerativeModel("gemini-2.5-flash")

# App title
st.title("Negative Keyworder")

# Inputs
target_keywords = st.text_area(
    "Enter Target Keywords",
    height=150
)

landing_page = st.text_input(
    "Enter Landing Page URL"
)

uploaded_file = st.file_uploader(
    "Upload Search Terms CSV",
    type=["csv"]
)

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if uploaded_file is not None:
    import pandas as pd

    df = pd.read_csv(uploaded_file)

    st.subheader("CSV Preview")
    st.dataframe(df.head())

    if df.empty:
        st.error("CSV is empty")
    else:
        search_column = df.columns[0]

        st.session_state.search_terms = "\n".join(
            df[search_column]
            .dropna()
            .astype(str)
            .tolist()
        )

def simple_cluster(terms):
    clusters = {
        "FREE / NON-COMMERCIAL": [],
        "CHEAP / LOW COST": [],
        "JOB / CAREER INTENT": [],
        "BRAND / NAVIGATIONAL": [],
        "COMMERCIAL INTENT": [],
        "OTHER": []
    }

    for t in terms:
        t_low = t.lower()

        if any(x in t_low for x in ["free", "grants", "gov", "government"]):
            clusters["FREE / NON-COMMERCIAL"].append(t)

        elif any(x in t_low for x in ["cheap", "low cost", "affordable"]):
            clusters["CHEAP / LOW COST"].append(t)

        elif any(x in t_low for x in ["job", "career", "salary", "hiring"]):
            clusters["JOB / CAREER INTENT"].append(t)

        elif any(x in t_low for x in ["login", "portal", "facebook", "amazon"]):
            clusters["BRAND / NAVIGATIONAL"].append(t)

        elif any(x in t_low for x in ["buy", "price", "cost", "quote", "service"]):
            clusters["COMMERCIAL INTENT"].append(t)

        else:
            clusters["OTHER"].append(t)

    return clusters

if st.button("Analyse Search Terms"):

    if not st.session_state.search_terms.strip():
        st.error("Please upload a CSV first.")
        st.stop()

    terms = st.session_state.search_terms.split("\n")
    clusters = simple_cluster(terms)

    prompt = f"""
You are a Google Ads negative keyword extraction engine.

Return ONLY valid JSON.

Do NOT output markdown, text, or explanation.

OUTPUT FORMAT MUST BE A JSON LIST:

[
  {{
    "negative_keyword": "",
    "match_type": "broad | phrase | exact",
    "reason": "",
    "affected_search_terms": []
  }}
]

TARGET KEYWORDS:
{target_keywords}

LANDING PAGE:
{landing_page}

CLUSTERED SEARCH TERMS:
{clusters}
"""

    response = model.generate_content(prompt)

    st.subheader("AI Analysis")
    st.text_area("Output", response.text, height=400)

    # -------------------------
    # EXPORT SECTION (FIXED)
    # -------------------------

    import json
    import pandas as pd

    try:
        data = json.loads(response.text)

        df_export = pd.json_normalize(data)

        st.subheader("Google Ads Paste Format")

        if not df_export.empty:

            paste_list = df_export["negative_keyword"].astype(str).tolist()
            paste_list = list(dict.fromkeys(paste_list))  # remove duplicates

            paste_format = "\n".join(paste_list)

            st.text_area(
                "Copy & Paste into Google Ads",
                value=paste_format,
                height=400
            )

            st.download_button(
                "Download Paste Format (.txt)",
                data=paste_format,
                file_name="google_ads_negative_keywords.txt",
                mime="text/plain"
            )

    except Exception:
        st.error("Could not parse AI output into structured format.")
        st.text(response.text)