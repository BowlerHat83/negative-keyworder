import json
import re
import google.generativeai as genai


# =====================================================
# SAFE GENERATION
# =====================================================
def safe_generate(model, prompt, set_error=None):
    try:
        res = model.generate_content(prompt)
        return res.text.strip()
    except Exception as e:

        err = str(e)

        if "429" in err or "quota" in err.lower():
            if set_error:
                set_error("E429", "Gemini quota exceeded")
            return None

        if set_error:
            set_error("E500", "Final classification error")

        return None


# =====================================================
# JSON PARSER
# =====================================================
def extract_json(text: str):
    if not text:
        return None

    try:
        return json.loads(text)
    except:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                return None
    return None


# =====================================================
# LAYER 7: FINAL CLASSIFICATION ENGINE
# =====================================================
def final_classification(roots: list, brand_model: dict, set_error=None):

    """
    Input:
        roots -> Layer 6 compressed negative roots
        brand_model -> Layer 3 intelligence

    Output:
        structured PPC-ready dataset
    """

    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""
You are a PPC Negative Keyword Expansion Engine.

You will take root negative keywords and expand them into:

1. Final Google Ads negative keyword list
2. AI-generated variations (synonyms, phrasing variants)
3. Review-safe ambiguous keywords
4. Positive-safe exclusions (do NOT negate)

-------------------------
INPUT ROOT NEGATIVES
-------------------------
{roots}

-------------------------
BRAND CONTEXT
-------------------------
{json.dumps(brand_model)}

-------------------------
TASK
-------------------------

Generate structured output:

{{
  "final_google_ads_negatives": [],
  "ai_negative_variations": [],
  "review_queue": [],
  "positives": [],
  "brand_summary": ""
}}

-------------------------
RULES
-------------------------

1. Expand ONLY from root negatives
2. Do NOT introduce unrelated industries
3. Variations must be PPC realistic (Google Ads style)
4. Keep review queue conservative
5. Positives must NOT overlap with negatives
6. Output MUST be valid JSON only

-------------------------
OUTPUT FORMAT ONLY
-------------------------
"""

    raw = safe_generate(model, prompt, set_error=set_error)

    data = extract_json(raw)

    # =====================================================
    # FALLBACK STRUCTURE
    # =====================================================
    if not data:
        return {
            "final_google_ads_negatives": [],
            "ai_negative_variations": [],
            "review_queue": [],
            "positives": [],
            "brand_summary": "Error or empty response"
        }

    # =====================================================
    # SAFETY NORMALISATION
    # =====================================================
    for k in [
        "final_google_ads_negatives",
        "ai_negative_variations",
        "review_queue",
        "positives"
    ]:
        if k not in data or data[k] is None:
            data[k] = []

    # =====================================================
    # DEDUPLICATION (IMPORTANT FOR ADS EXPORT)
    # =====================================================
    data["final_google_ads_negatives"] = list(set(data["final_google_ads_negatives"]))
    data["ai_negative_variations"] = list(set(data["ai_negative_variations"]))

    return data
