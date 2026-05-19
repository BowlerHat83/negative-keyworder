def score_confidence(term, roots, reviews, positives):

    t = term.lower()

    score = 1.0

    # review penalty (uncertainty)
    if any(r.lower() in t for r in reviews):
        score -= 0.25

    # positive overlap penalty (high risk signal)
    if any(p.lower() in t for p in positives):
        score -= 0.5

    # root context adjustment
    matched_roots = [r for r in roots if r in t]

    if matched_roots:

        if len(t.split()) > 1:
            score -= 0.15  # phrase complexity penalty

    # clamp
    return max(0.0, min(1.0, score))


# =====================================================
# UPDATED LAYER 8 OUTPUT BUILDER
# =====================================================

def build_layer8_output_v2(layer6, layer7, brand_summary, ai_variations):

    negatives = set(layer6.get("negative", []))
    reviews = set(layer6.get("review", []))
    positives = set(layer6.get("positive", []))

    roots = set(layer7 or [])

    # remove positives from negatives
    negatives = {n for n in negatives if n not in positives}

    search_term_negatives = []

    # =========================
    # ADD CONFIDENCE SCORING
    # =========================

    for term in negatives:

        confidence = score_confidence(
            term,
            roots,
            reviews,
            positives
        )

        # determine type
        t = term.lower()

        if len(t.split()) == 1:
            match_type = "broad"
        else:
            match_type = "phrase"

        search_term_negatives.append({
            "term": term,
            "confidence": round(confidence, 3),
            "type": match_type
        })

    # =========================
    # GOOGLE ADS EXPORT
    # =========================

    google_ads_list = []

    for item in search_term_negatives:

        term = item["term"]

        if item["type"] == "phrase":
            google_ads_list.append(f'"{term}"')
        else:
            google_ads_list.append(term)

    # include AI variations (no scoring yet, keep simple)
    for v in ai_variations:
        if v not in positives:
            if " " in v:
                google_ads_list.append(f'"{v}"')
            else:
                google_ads_list.append(v)

    return {
        "brand_summary": brand_summary,
        "review_queue": sorted(reviews),

        # OUTPUT 3 UPDATED
        "search_term_negatives": search_term_negatives,

        "ai_variations": sorted(set(ai_variations)),

        "google_ads_export": "\n".join(sorted(set(google_ads_list))),

        "positive_keywords": sorted(positives)
    }
