import json
import re
import google.generativeai as genai


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
    set_error=None
):

    # safety: empty batch
    if not batch_terms:
        return {"negative": [], "review": [], "positive": []}

    formatted_terms = "\n".join([f"- {t}" for t in batch_terms])

    prompt = f"""
You are a strict PPC classification engine.

Your job:
Classify EACH search term into exactly ONE category:

- negative
- review
- positive

-------------------------
CRITICAL RULES
-------------------------

1. Every term MUST be classified
2. Do NOT skip any term
3. Do NOT invent new terms
4. Output MUST be valid JSON only
5. If unsure → review

-------------------------
BRAND CONTEXT
-------------------------

{json.dumps(brand)}

-------------------------
CAMPAIGN TYPE
{campaign_type}

TARGET KEYWORDS
{target_keywords}

-------------------------
SEARCH TERMS
{formatted_terms}

-------------------------
OUTPUT FORMAT (STRICT JSON ONLY)

{{
  "negative": [],
  "review": [],
  "positive": []
}}
"""

    raw = safe_generate(model, prompt, set_error=set_error)

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
        data["review"].extend(missing)

    return data
