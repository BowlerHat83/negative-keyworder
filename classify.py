import json
import re
import time

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
            set_error("E500", "AI generation error")

        return None


# =====================================================
# JSON PARSER (ROBUST)
# =====================================================

def extract_json(text: str):

    if not text:
        return None

    try:
        return json.loads(text)
    except:

        match = re.search(r"\{.*\}", text, re.DOTALL)

        if match:
            try:
                return json.loads(match.group())
            except:
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
    set_error=None
):

    """
    Core PPC classification engine.
    """

    formatted_terms = "\n".join([f"- {t}" for t in batch_terms])

    prompt = f"""
You are a senior PPC search term classification engine.

You classify search terms into:
- negative (irrelevant traffic)
- review (uncertain intent)
- positive (commercially valuable)

---

CRITICAL RULES:

1. BRAND CONTEXT IS PRIMARY:
Interpret meaning using brand positioning:

- luxury brand → "cheap" = negative
- budget brand → "cheap" = positive
- SaaS → "used" = irrelevant
- car dealership → "used" = positive

2. DO NOT INVENT INTENT:
Only classify based on provided terms.

3. DEFAULT TO SAFETY:
If unsure → review (NOT negative)

4. COMMERCIAL INTENT PRIORITY:
If a term implies purchase intent → avoid marking negative unless clearly irrelevant

---

OUTPUT FORMAT (STRICT JSON ONLY):

{{
  "negative": [],
  "review": [],
  "positive": []
}}

---

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

---

BRAND CONTEXT:
{json.dumps(brand)}

---

SEARCH TERMS:
{formatted_terms}
"""

    raw = safe_generate(model, prompt, set_error=set_error)

    if not raw:
        return {
            "negative": [],
            "review": [],
            "positive": []
        }

    data = extract_json(raw)

    if not data:
        return {
            "negative": [],
            "review": [],
            "positive": []
        }

    # =====================================================
    # NORMALISATION SAFETY
    # =====================================================

    for key in ["negative", "review", "positive"]:
        if key not in data or data[key] is None:
            data[key] = []

    return data
