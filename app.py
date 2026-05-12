import streamlit as st
import google.generativeai as genai
import json
import re
import pandas as pd

# -------------------------
# CONFIG
# -------------------------
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

st.title("Negative Keyworder")

# -------------------------
# HELPERS
# -------------------------
def extract_json(text):
    text = text.strip()
    text = re.sub(r"```json|```", "", text)

    start = text.find("[")
    end = text.rfind("]")

    if start == -1 or end == -1:
        raise ValueError("No JSON found")

    return json.loads(text[start:end+1])


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

        if any(x in t_low for x in ["free", "gov", "government", "grants"]):
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


# -------------------------
# INPUTS
# -------------------------
target_keywords = st.text_area("Enter Target Keywords", height=150)
landing_page = st.text_input("Enter Landing Page URL")

uploaded_file = st.file_uploader("Upload Search Terms CSV", type=["csv"])

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    st.subheader("CSV Preview")
    st.dataframe(df.head())

    if not df.empty:
        col = df.columns[0]
        st.session_state.search_terms = "\n".join(
            df[col].dropna().astype(str).tolist()
        )


# -------------------------
# MAIN ACTION
# -------------------------
if st.button("Analyse Search Terms"):

    if not st.session_state.search_terms.strip():
        st.error("Please upload a CSV first.")
        st.stop()

    terms = st.session_state.search_terms.split("\n")
    clusters = simple_cluster(terms)

    prompt = f"""
You are a Google Ads negative keyword extraction engine.

Return ONLY valid JSON.

OUTPUT FORMAT:
[
  {{
    "negative_keyword": "",
    "match_type": "broad | phrase | exact",
    "reason": "",
    "affected_search_terms": []
  }}
]

RULES:
- Only use provided search terms
- Do not invent keywords
- Return valid JSON only

TARGET KEYWORDS:
{target_keywords}

LANDING PAGE:
{landing_page}

CLUSTERED SEARCH TERMS:
{json.dumps(clusters, indent=2)}
"""

    response = model.generate_content(prompt)
    raw_output = response.text

    st.subheader("AI Output")
    st.text_area("Raw Response", raw_output, height=300)

    # -------------------------
    # PARSE + EXPORT
    # -------------------------
    try:
        data = extract_json(raw_output)
        df_export = pd.json_normalize(data)

        st.subheader("Google Ads Paste Format")

        if not df_export.empty:

            keywords = df_export["negative_keyword"].dropna().astype(str).tolist()
            keywords = list(dict.fromkeys(keywords))

            paste = "\n".join(keywords)

            st.text_area("Copy & Paste into Google Ads", paste, height=300)

            st.download_button(
                "Download TXT",
                data=paste,
                file_name="negative_keywords.txt",
                mime="text/plain"
            )

    except Exception:
        st.error("Failed to parse AI output. Showing raw response.")
        st.text(raw_output)
