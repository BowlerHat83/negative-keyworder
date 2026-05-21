import json
import re
from typing import List, Dict, Any

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
# CLASSIFICATION ENGINE
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

    prompt = f"""
You are a high-precision PPC search term classifier.

Assign each term to exactly ONE category:
- negative
- review
- positive

Return ONLY valid JSON.

{{
  "negative": [],
  "review": [],
  "positive": []
}}

RULES:
{rules}

BRAND CONTEXT:
{json.dumps(brand, indent=2)}

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

SEARCH TERMS:
{formatted_terms}

No explanations. JSON only.
"""

    raw = safe_generate(model, prompt)
    data = extract_json(raw)

    # =====================================================
    # FAILSAFE
    # =====================================================
    if not data:
        return {
            "negative": batch_terms,
            "review": [],
            "positive": []
        }

    data.setdefault("negative", [])
    data.setdefault("review", [])
    data.setdefault("positive", [])

    # =====================================================
    # LOSSLESS GUARANTEE
    # =====================================================
    classified = set(data["negative"] + data["review"] + data["positive"])
    missing = [t for t in batch_terms if t not in classified]

    if missing:
        data["review"].extend(missing)

    # =====================================================
    # DEDUP
    # =====================================================
    for k in ["negative", "review", "positive"]:
        data[k] = list(dict.fromkeys(data[k]))

    # =====================================================
    # REVIEW SAFETY CAP
    # =====================================================
    if len(data["review"]) > len(batch_terms) * 0.6:
        overflow = data["review"][int(len(batch_terms) * 0.6):]
        data["review"] = data["review"][:int(len(batch_terms) * 0.6)]
        data["negative"].extend(overflow)

    return data
