# =====================================================
# CONTEXT MODULE (BRAND INTELLIGENCE + PREFILTER)
# =====================================================
import re
import json
import google.generativeai as genai
from typing import List, Tuple, Dict, Any

# =====================================================
# MODEL INIT (FIX #1 — CRITICAL)
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")


# =====================================================
# SAFE GENERATION
# =====================================================
def safe_generate(prompt: str):
    try:
        response = model.generate_content(prompt)
        if not response or not response.text:
            return None
        return response.text.strip()
    except Exception:
        return None


# =====================================================
# JSON PARSER (ROBUST FIX)
# =====================================================
def extract_json(text: str):
    if not text:
        return None

    # direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # extract fenced JSON
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            return None

    return None


# =====================================================
# BRAND MODEL BUILDER (IMPROVED PROMPT)
# =====================================================
def build_context(page_text: str, target_keywords: str, campaign_type: str) -> Dict[str, Any]:

    prompt = f"""
You are a PPC Brand Intelligence Engine.

Your job is to extract structured brand intelligence from website content.

IMPORTANT:
- Return valid JSON only
- Do not wrap in markdown
- Do not include commentary

OUTPUT FORMAT:
{{
  "positioning": ["..."],
  "price_positioning": ["..."],
  "intent_profile": {{
    "commercial": "high | medium | low",
    "informational": "high | medium | low",
    "lead_generation": "high | medium | low"
  }},
  "core_offerings": ["..."],
  "safe_roots": ["..."],
  "risk_terms": ["..."],
  "low_value_intents": ["..."],
  "negative_bias_rules": ["..."]
}}

CAMPAIGN TYPE:
{campaign_type}

TARGET KEYWORDS:
{target_keywords}

PAGE CONTENT:
{page_text[:6000]}
"""

    raw = safe_generate(prompt)
    data = extract_json(raw)

    # =====================================================
    # FALLBACK FIX (CRITICAL — PREVENT EMPTY OUTPUTS)
    # =====================================================
    if not data:
        return {
            "positioning": ["unknown positioning"],
            "price_positioning": ["unknown"],
            "intent_profile": {
                "commercial": "medium",
                "informational": "medium",
                "lead_generation": "medium"
            },
            "core_offerings": ["unable to extract — fallback active"],
            "safe_roots": [],
            "risk_terms": [],
            "low_value_intents": [],
            "negative_bias_rules": []
        }

    # =====================================================
    # SAFE NORMALISATION
    # =====================================================
    defaults = {
        "positioning": [],
        "price_positioning": [],
        "core_offerings": [],
        "safe_roots": [],
        "risk_terms": [],
        "low_value_intents": [],
        "negative_bias_rules": []
    }

    for k, v in defaults.items():
        data.setdefault(k, v)

    data.setdefault("intent_profile", {
        "commercial": "medium",
        "informational": "medium",
        "lead_generation": "medium"
    })

    return data


# =====================================================
# NORMALISATION
# =====================================================
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


# =====================================================
# PREFILTER ENGINE (UNCHANGED LOGIC, SAFE FIXES)
# =====================================================
def contextual_prefilter(
    terms: List[str],
    brand_model: Dict[str, Any]
) -> Tuple[List[str], List[str]]:

    auto_negative = []
    remaining = []

    safe_roots = set(normalize(x) for x in brand_model.get("safe_roots", []))
    low_value = set(normalize(x) for x in brand_model.get("low_value_intents", []))
    risk_terms = set(normalize(x) for x in brand_model.get("risk_terms", []))
    bias_rules = brand_model.get("negative_bias_rules", [])
    positioning = set(normalize(x) for x in brand_model.get("positioning", []))
    intent_profile = brand_model.get("intent_profile", {})

    def is_low_value(t: str) -> bool:
        return any(sig in t for sig in low_value)

    def is_safe(t: str) -> bool:
        return any(root in t for root in safe_roots)

    def is_risk(t: str) -> bool:
        return any(r in t for r in risk_terms)

    def apply_bias(t: str) -> bool:
        for rule in bias_rules:
            r = normalize(rule)

            if "cheap" in r and "luxury" in positioning:
                if "cheap" in t:
                    return True

            if "free" in r and intent_profile.get("commercial") == "high":
                if "free" in t:
                    return True

        return False

    for term in terms:

        t = normalize(term)

        if is_safe(t):
            remaining.append(term)
            continue

        if is_risk(t):
            remaining.append(term)
            continue

        if is_low_value(t):
            auto_negative.append(term)
            continue

        if apply_bias(t):
            auto_negative.append(term)
            continue

        remaining.append(term)

    return auto_negative, remaining
