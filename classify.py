import json
import re

"""
This module is the ONLY classification engine.

It returns:
- negative
- review
- positive

No downstream module may override outputs.
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

        if "429" in err or "quota" in err.lower():
            if set_error:
                set_error("E429", "Gemini quota exceeded")
            return None

        if set_error:
            set_error("E500", "Gemini classification error")

        return None


# =====================================================
# JSON PARSER
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
# CLASSIFICATION ENGINE (IMPROVED STABILITY LAYER)
# =====================================================
def classify_terms_batch(
    model,
    batch_terms,
    brand,
    campaign_type,
    target_keywords,
    rules
):

    if not batch_terms:
        return {"negative": [], "review": [], "positive": []}

    formatted_terms = "\n".join(f"- {t}" for t in batch_terms)

    # =====================================================
    # ENHANCED PROMPT DISCIPLINE
    # (key change: removes ambiguity clustering + enforces separation pressure)
    # =====================================================
    prompt = f"""
You are a high-precision PPC search term classifier.

Your job is to assign each term to ONE category:
- negative
- review
- positive

Return ONLY valid JSON.

========================
OUTPUT FORMAT (STRICT)
========================
{{
  "negative": [],
  "review": [],
  "positive": []
}}

========================
CLASSIFICATION RULES
========================

{rules}

========================
CRITICAL BEHAVIOURAL FIXES
========================

1. DO NOT cluster uncertainty into REVIEW
   - REVIEW is ONLY for true ambiguity between NEGATIVE and POSITIVE

2. Avoid neutral scoring behaviour
   - You must choose direction unless truly unclear

3. NEGATIVE is NOT default in output
   - It is only default in uncertainty, not behaviour

4. REVIEW BAND RULE
   - Use REVIEW ONLY if:
     - term could realistically be BOTH commercial and non-commercial
     - AND brand context does not clearly resolve it

5. POSITIVE RULE
   - If any strong commercial intent exists → prefer POSITIVE over REVIEW

========================
BRAND CONTEXT
========================
{json.dumps(brand, indent=2)}

========================
CAMPAIGN TYPE
========================
{campaign_type}

========================
TARGET KEYWORDS
========================
{target_keywords}

========================
SEARCH TERMS
========================
{formatted_terms}

========================
HARD OUTPUT REQUIREMENTS
========================
- Every term must appear in exactly ONE category
- No explanations
- JSON only
"""

    raw = safe_generate(model, prompt)

    data = extract_json(raw)

    # =====================================================
    # FAILSAFE (NO LOSS GUARANTEE)
    # =====================================================
    if not data:
        return {
            "negative": batch_terms,
            "review": [],
            "positive": []
        }

    # =====================================================
    # NORMALISATION SAFETY
    # =====================================================
    data.setdefault("negative", [])
    data.setdefault("review", [])
    data.setdefault("positive", [])

    # =====================================================
    # LOSSLESS GUARANTEE (CRITICAL)
    # ensures no silent drops
    # =====================================================
    classified = set(
        data["negative"]
        + data["review"]
        + data["positive"]
    )

    missing = [t for t in batch_terms if t not in classified]

    # IMPORTANT CHANGE:
    # missing terms go to REVIEW first, NOT NEGATIVE
    # (prevents artificial bias inflation)
    if missing:
        data["review"].extend(missing)

    # =====================================================
    # DEDUPLICATION (ORDER PRESERVED)
    # =====================================================
    for k in ["negative", "review", "positive"]:
        data[k] = list(dict.fromkeys(data[k]))

    # =====================================================
    # FINAL STABILITY RULE
    # prevent REVIEW explosion
    # =====================================================
    if len(data["review"]) > len(batch_terms) * 0.6:
        # fallback safety: push weak review back to negative
        overflow = data["review"][int(len(batch_terms)*0.6):]
        data["review"] = data["review"][:int(len(batch_terms)*0.6)]
        data["negative"].extend(overflow)

    return data
