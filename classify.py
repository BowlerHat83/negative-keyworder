import json
import re
import google.generativeai as genai

"""
This is the ONLY decision layer.

It is responsible for:
- negative classification
- review classification
- positive classification

No other module may override decisions.
"""

# =====================================================
# SAFE GENERATION WRAPPER
# =====================================================
def safe_generate(model, prompt, set_error=None):

    try:
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:

        err = str(e)

        # quota handling
        if "429" in err or "quota" in err.lower():
            if set_error:
                set_error("E429", "Gemini quota exceeded")
            return None

        if set_error:
            set_error("E500", "Gemini classification error")

        return None


# =====================================================
# JSON PARSER (STRICT)
# =====================================================
def extract_json(text: str):
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return None

    return None


# =====================================================
# LAYER 5: CLASSIFICATION ENGINE
# =====================================================
def classify_terms_batch(
    model,
    batch_terms,
    brand,
    campaign_type,
    target_keywords,
    rules
):

    # safety: empty batch
    if not batch_terms:
        return {"negative": [], "review": [], "positive": []}

    formatted_terms = "\n".join([f"- {t}" for t in batch_terms])

    prompt = f"""
You are an aggressive Google Ads negative keyword strategist.

Your task:
Remove wasted traffic aggressively.

Your PRIMARY goal is:
MAXIMISE irrelevant traffic exclusion.

You are NOT cautious.
You are NOT conservative.
You do NOT protect edge-case traffic.

------------------------------------------------
CLASSIFICATION TYPES
------------------------------------------------

NEGATIVE:
- irrelevant
- low intent
- informational
- job seekers
- free users
- DIY intent
- research intent
- competitors
- weak relevance
- vague intent
- poor commercial fit

POSITIVE:
- clearly aligned commercial intent
- directly relevant to target offering

REVIEW:
- use ONLY in rare cases
- use ONLY if traffic could realistically convert
- REVIEW should normally be under 10% of terms

------------------------------------------------
DECISION POLICY
------------------------------------------------

DEFAULT TO NEGATIVE.

If uncertain:
NEGATIVE.

If partially relevant:
NEGATIVE.

If weak intent:
NEGATIVE.

Only classify as REVIEW if excluding the term could realistically damage campaign performance.

------------------------------------------------
STRICT RULES
------------------------------------------------

1. Every term MUST be classified
2. Never skip terms
3. Never invent terms
4. Output valid JSON only
5. Do NOT explain reasoning

------------------------------------------------
BRAND CONTEXT
------------------------------------------------

{json.dumps(brand)}

------------------------------------------------
CAMPAIGN TYPE
------------------------------------------------

{campaign_type}

------------------------------------------------
TARGET KEYWORDS
------------------------------------------------

{target_keywords}

------------------------------------------------
SEARCH TERMS
------------------------------------------------

{formatted_terms}

------------------------------------------------
OUTPUT FORMAT
------------------------------------------------

{{
  "negative": [],
  "review": [],
  "positive": []
}}
"""

    raw = safe_generate(model, prompt)

    data = extract_json(raw)

    # =====================================================
    # FAILSAFE STRUCTURE
    # =====================================================
    if not data:
        return {
            "negative": [],
            "review": batch_terms,   # safe fallback
            "positive": []
        }

    # =====================================================
    # NORMALISATION SAFETY
    # =====================================================
    for key in ["negative", "review", "positive"]:
        if key not in data or data[key] is None:
            data[key] = []

    # =====================================================
    # LOSSLESS GUARANTEE (IMPORTANT)
    # ensure no term is dropped
    # =====================================================
    all_classified = set(
        data["negative"] + data["review"] + data["positive"]
    )

    missing = [t for t in batch_terms if t not in all_classified]

    if missing:
        data["negative"].extend(missing)

    return data
