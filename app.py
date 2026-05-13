import streamlit as st
import google.generativeai as genai
import pandas as pd

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

st.title("Negative Keyworder")

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


target_keywords = st.text_area("Enter Target Keywords", height=150)
landing_page = st.text_input("Landing Page URL")

uploaded_file = st.file_uploader("Upload Search Terms CSV", type=["csv"])

if "search_terms" not in st.session_state:
    st.session_state.search_terms = ""

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    if not df.empty:
        col = df.columns[0]
        st.session_state.search_terms = "\n".join(df[col].dropna().astype(str).tolist())

if st.button("Analyse Search Terms"):

    if not st.session_state.search_terms.strip():
        st.error("Please upload a CSV first.")
        st.stop()

    terms = st.session_state.search_terms.split("\n")
    clusters = simple_cluster(terms)

    prompt = f"""
You are a Google Ads negative keyword generator.

Return ONLY copy-paste formatted keywords.

FORMAT:
broad: keyword
phrase: "keyword"
exact: [keyword]

RULES:
- one per line
- no explanation
- no JSON
- no markdown
- choose correct match type when needed

TARGET KEYWORDS:
{target_keywords if target_keywords.strip() else "None"}

LANDING PAGE:
{landing_page}

SEARCH TERMS:
{chr(10).join(terms[:300])}
"""

    response = model.generate_content(prompt)
    raw_output = response.text.strip()

    st.subheader("Google Ads Paste Format")

    st.text_area("Copy & Paste", raw_output, height=400)

    st.download_button(
        "Download TXT",
        raw_output,
        "negative_keywords.txt",
        "text/plain"
    )
