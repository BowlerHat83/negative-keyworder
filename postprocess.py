import json
import re
import google.generativeai as genai
from typing import List, Dict, Any


# =====================================================
# MODEL (FINAL EXPANSION ONLY)
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
    except:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                return None
    return None


# =====================================================
# LAYER 6 — ROOT EXTRACTION
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

    return sorted(roots)


# =====================================================
# LAYER 7 — FINAL EXPANSION ENGINE
# =====================================================
def final_classification(roots: list, brand_model: dict, set_error=None):

    prompt = f"""
You are a PPC Negative Keyword Expansion Engine.

Expand root negatives into PPC-ready outputs.

INPUT ROOTS:
{roots}

BRAND CONTEXT:
{json.dumps(brand_model)}

OUTPUT JSON ONLY:

{{
  "final_google_ads_negatives": [],
  "ai_negative_variations": [],
  "review_queue": [],
  "positives": [],
  "brand_summary": ""
}}

RULES:
- expand ONLY from roots
- no external invention
- keep review minimal
- maintain PPC realism
- output valid JSON only
"""

    raw = safe_generate(model, prompt, set_error=set_error)
    data = extract_json(raw)

    if not data:
        return {
            "final_google_ads_negatives": [],
            "ai_negative_variations": [],
            "review_queue": [],
            "positives": [],
            "brand_summary": "Error or empty response"
        }

    for k in [
        "final_google_ads_negatives",
        "ai_negative_variations",
        "review_queue",
        "positives"
    ]:
        if k not in data or data[k] is None:
            data[k] = []

    data["final_google_ads_negatives"] = list(set(data["final_google_ads_negatives"]))
    data["ai_negative_variations"] = list(set(data["ai_negative_variations"]))

    return data


# =====================================================
# LAYER 8 — OUTPUT AGGREGATION
# =====================================================
def build_outputs(
    brand_model: Dict[str, Any],
    layer5_data: Dict[str, Any],
    layer6_roots,
    layer7_data: Dict[str, Any]
) -> Dict[str, Any]:

    brand_summary = {
        "positioning": brand_model.get("positioning"),
        "price_positioning": brand_model.get("price_positioning"),
        "intent_profile": brand_model.get("intent_profile", "unknown"),
        "core_offerings": brand_model.get("core_offerings", []),
        "safe_roots": brand_model.get("safe_roots", []),
        "risk_terms": brand_model.get("risk_terms", [])
    }

    review_queue = layer5_data.get("review", [])
    negatives_with_roots = layer6_roots or []
    ai_variations = layer7_data.get("ai_negative_variations", [])

    raw_ads = layer7_data.get("final_google_ads_negatives", [])

    final_google_ads = "\n".join(sorted(set(raw_ads))) if isinstance(raw_ads, list) else str(raw_ads)

    return {
        "brand_summary": brand_summary,
        "review_queue": review_queue,
        "negatives_with_roots": negatives_with_roots,
        "ai_variations": ai_variations,
        "final_google_ads": final_google_ads
    }
