import json
import re
import google.generativeai as genai
from typing import List, Dict, Any


# =====================================================
# MODEL (IDEALLY SHOULD BE IN APP.PY, BUT KEPT SAFE HERE)
# =====================================================
model = genai.GenerativeModel("gemini-2.5-flash")


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
            set_error("E500", "Postprocess error")

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
            except:
                return None

    return None


# =====================================================
# ROOT EXTRACTION (LAYER 6)
# =====================================================
def extract_roots_protected(
    negative_terms: List[str],
    review_terms: List[str],
    positive_terms: List[str],
    brand_model: Dict
) -> List[str]:

    intent_vocab = {
        "job", "jobs",
        "career", "careers",
        "salary", "salaries",
        "free",
        "cheap",
        "template", "templates",
        "download",
        "tutorial",
        "guide",
        "pdf",
        "how"
    }

    protected_terms = set(
        t.lower().strip()
        for t in (review_terms + positive_terms)
        if t
    )

    protected_roots = set(
        x.lower().strip()
        for x in brand_model.get("safe_roots", [])
        if x
    )

    roots = set()

    for term in negative_terms:

        if not term:
            continue

        t = term.lower().strip()

        if t in protected_terms:
            continue

        for w in t.split():

            if w in protected_roots:
                continue

            if w in intent_vocab:
                roots.add(w)

    return sorted(list(roots))


# =====================================================
# FINAL EXPANSION ENGINE (LAYER 7)
# =====================================================
def final_classification(roots: list, brand_model: dict, set_error=None):

    prompt = f"""
You are a PPC Negative Keyword Expansion Engine.

Expand root negatives into PPC-ready outputs.

ROOTS:
{roots}

BRAND CONTEXT:
{json.dumps(brand_model, indent=2)}

Return ONLY valid JSON:

{{
  "final_google_ads_negatives": [],
  "ai_negative_variations": [],
  "review_queue": [],
  "brand_summary": ""
}}

RULES:
- expand ONLY from roots
- no external invention
- keep review minimal
- PPC-safe outputs only
"""

    raw = safe_generate(model, prompt, set_error=set_error)
    data = extract_json(raw)

    if not data:
        return {
            "final_google_ads_negatives": [],
            "ai_negative_variations": [],
            "review_queue": [],
            "brand_summary": "Error or empty response"
        }

    # safety defaults
    data.setdefault("final_google_ads_negatives", [])
    data.setdefault("ai_negative_variations", [])
    data.setdefault("review_queue", [])
    data.setdefault("brand_summary", "")

    # dedupe lists
    data["final_google_ads_negatives"] = list(set(data["final_google_ads_negatives"]))
    data["ai_negative_variations"] = list(set(data["ai_negative_variations"]))

    return data


# =====================================================
# OUTPUT AGGREGATION (LAYER 8)
# =====================================================
def build_outputs(
    brand_model: Dict[str, Any],
    layer5_data: Dict[str, Any],
    layer6_roots: List[str],
    layer7_data: Dict[str, Any]
) -> Dict[str, Any]:

    brand_summary = {
        "positioning": brand_model.get("positioning"),
        "price_positioning": brand_model.get("price_positioning"),
        "intent_profile": brand_model.get("intent_profile", {}),
        "core_offerings": brand_model.get("core_offerings", []),
        "safe_roots": brand_model.get("safe_roots", []),
        "risk_terms": brand_model.get("risk_terms", [])
    }

    review_queue = layer5_data.get("review", [])
    ai_variations = layer7_data.get("ai_negative_variations", [])

    raw_ads = layer7_data.get("final_google_ads_negatives", [])
    final_google_ads = "\n".join(sorted(set(raw_ads))) if isinstance(raw_ads, list) else str(raw_ads)

    return {
        "brand_summary": brand_summary,
        "review_queue": review_queue,
        "roots": layer6_roots,
        "ai_negative_variations": ai_variations,
        "final_google_ads": final_google_ads
    }
