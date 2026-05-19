from typing import Dict, Any


# =====================================================
# LAYER 8: OUTPUT AGGREGATION
# =====================================================
def build_outputs(
    brand_model: Dict[str, Any],
    layer5_data: Dict[str, Any],
    layer6_roots,
    layer7_data: Dict[str, Any]
) -> Dict[str, Any]:

    """
    Aggregates outputs from all pipeline layers into UI-ready structure.

    IMPORTANT:
    - No logic or classification
    - Only composition + formatting
    """

    # =====================================================
    # 1. BRAND SUMMARY (LAYER 3)
    # =====================================================
    brand_summary = {
        "business_type": brand_model.get("business_type"),
        "positioning": brand_model.get("positioning"),
        "price_positioning": brand_model.get("price_positioning"),
        "intent_profile": brand_model.get("intent_profile", "unknown"),
        "core_offerings": brand_model.get("core_offerings", []),
        "safe_roots": brand_model.get("safe_roots", []),
        "risk_terms": brand_model.get("risk_terms", [])
    }

    # =====================================================
    # 2. REVIEW QUEUE (LAYER 5)
    # =====================================================
    review_queue = layer5_data.get("review", [])

    # =====================================================
    # 3. ROOT NEGATIVES (LAYER 6)
    # =====================================================
    negatives_with_roots = layer6_roots if layer6_roots else []

    # =====================================================
    # 4. AI VARIATIONS (LAYER 7)
    # =====================================================
    ai_variations = layer7_data.get("ai_variations", [])

    # =====================================================
    # 5. FINAL GOOGLE ADS OUTPUT (LAYER 7)
    # =====================================================
    raw_ads = layer7_data.get("final_google_ads_list", [])

    if isinstance(raw_ads, list):
        final_google_ads = "\n".join(sorted(set(raw_ads)))
    else:
        final_google_ads = str(raw_ads)

    # =====================================================
    # RETURN STRUCTURE
    # =====================================================
    return {
        "brand_summary": brand_summary,
        "review_queue": review_queue,
        "negatives_with_roots": negatives_with_roots,
        "ai_variations": ai_variations,
        "final_google_ads": final_google_ads
    }
