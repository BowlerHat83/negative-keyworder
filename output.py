from typing import Dict, Any


# =====================================================
# LAYER 8: OUTPUT AGGREGATION LAYER
# =====================================================
def build_outputs(
    brand_model: Dict[str, Any],
    layer5_data: Dict[str, Any],
    layer6_roots: Any,
    layer7_data: Dict[str, Any]
) -> Dict[str, Any]:

    """
    Aggregates outputs from multiple pipeline layers.

    THIS LAYER:
    - Does NOT classify
    - Does NOT generate AI output
    - ONLY composes final UI-ready structures
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
    # 3. NEGATIVES (LAYER 6 ROOT OUTPUT)
    # =====================================================
    negatives_with_roots = layer6_roots if layer6_roots else []

    # =====================================================
    # 4. AI VARIATIONS (LAYER 7)
    # =====================================================
    ai_variations = layer7_data.get("ai_variations", [])

    # =====================================================
    # 5. FINAL GOOGLE ADS LIST (LAYER 7 CLEAN OUTPUT)
    # =====================================================
    final_ads_list = layer7_data.get("final_google_ads_list", [])

    # safety fallback: ensure string format for UI
    if isinstance(final_ads_list, list):
        final_google_ads = "\n".join(sorted(set(final_ads_list)))
    else:
        final_google_ads = str(final_ads_list)

    # =====================================================
    # RETURN UI STRUCTURE
    # =====================================================
    return {
        "brand_summary": brand_summary,
        "review_queue": review_queue,
        "negatives_with_roots": negatives_with_roots,
        "ai_variations": ai_variations,
        "final_google_ads": final_google_ads
    }
