import google.generativeai as genai
import json
import re

# =====================================================
# MODEL
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")


# =====================================================
# SAFE GENERATION WRAPPER
# =====================================================
def safe_generate(prompt: str):
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return None


# =====================================================
# JSON PARSER (robust fallback)
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
# LAYER 3 — BRAND INTELLIGENCE ENGINE
# =====================================================
def build_brand_model(page_text: str, target_keywords: str, campaign_type: str):

    prompt = f"""
You are a PPC Brand Intelligence Engine.

You do NOT classify keywords.
You do NOT filter search terms.
You do NOT apply rules.

You ONLY extract structured brand understanding for downstream systems.

---

RETURN ONLY VALID JSON (no commentary).

---

OUTPUT SCHEMA (STRICT):

{{
  "positioning": [
    "luxury",
    "budget",
    "premium",
    "enterprise",
    "mid-market",
    "new",
    "used"
  ],

  "price_positioning": [
    "cheap",
    "affordable",
    "expensive",
    "high-ticket"
  ],

  "intent_profile": {{
    "commercial": "high | medium | low",
    "informational": "high | medium | low",
    "lead_generation": "high | medium | low"
  }},

  "core_offerings": [],

  "safe_roots": [],

  "risk_terms": [],

  "low_value_intents": [],

  "negative_bias_rules": []
}}

---

GUIDELINES:

1. Extract meaning ONLY from the landing page content.
2. Do NOT use generic marketing assumptions.
3. Do NOT apply keyword filtering logic.
4. Do NOT decide what is negative or positive.
5. Identify brand positioning based on evidence in text.
6. Identify intent profile based on business model signals.
7. Risk terms must be context-dependent ambiguous terms.
8. Low value intents must be relative to THIS brand only.
9. Negative bias rules must describe interpretation logic, NOT actions.

---

POSITIONING EXAMPLES:
- luxury / premium / budget / enterprise / mid-market / new / used

PRICE POSITIONING:
- cheap / affordable / expensive / high-ticket

INTENT PROFILE:
- commercial = likelihood of purchase intent
- informational = research intent strength
- lead_generation = inquiry/contact intent strength

---

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

---

LANDING PAGE CONTENT:
{page_text[:7000]}
"""

    raw = safe_generate(prompt)
    data = extract_json(raw) if raw else None

    # =====================================================
    # FALLBACK SAFE MODEL (ensures system never breaks)
    # =====================================================
    if not data:
        return {
            "positioning": ["unknown"],
            "price_positioning": ["unknown"],
            "intent_profile": {
                "commercial": "medium",
                "informational": "medium",
                "lead_generation": "medium"
            },
            "core_offerings": [],
            "safe_roots": [],
            "risk_terms": [],
            "low_value_intents": [],
            "negative_bias_rules": []
        }

    # =====================================================
    # NORMALISATION SAFETY
    # =====================================================
    for key in [
        "positioning",
        "price_positioning",
        "core_offerings",
        "safe_roots",
        "risk_terms",
        "low_value_intents",
        "negative_bias_rules"
    ]:
        if key not in data or data[key] is None:
            data[key] = []

    if "intent_profile" not in data or data["intent_profile"] is None:
        data["intent_profile"] = {
            "commercial": "medium",
            "informational": "medium",
            "lead_generation": "medium"
        }

    return data
