# =====================================================
# LAYER 8 — INTENT RECONCILIATION ENGINE
# =====================================================

def resolve_layer8(layer6, layer7, campaign_type="Search"):
    """
    Final decision layer:
    - resolves negatives
    - protects positives
    - preserves review queue
    - applies root-based filtering safely
    """

    # =====================================================
    # INPUTS
    # =====================================================

    negatives = set(layer6.get("negative", []))
    reviews = set(layer6.get("review", []))
    positives = set(layer6.get("positive", []))

    roots = set(layer7 or [])

    final_broad = set()
    final_phrase = set()

    # =====================================================
    # 1. PROTECT POSITIVE TERMS (NEVER NEGATIVE THEM)
    # =====================================================

    negatives = {n for n in negatives if n not in positives}

    # =====================================================
    # 2. REVIEW TERMS PASS THROUGH (NO AUTOMATION)
    # =====================================================

    review_output = sorted(reviews)

    # =====================================================
    # 3. NEGATIVE RESOLUTION
    # =====================================================

    for term in negatives:

        t = term.lower().strip()
        words = t.split()

        matched_roots = [r for r in roots if r in t]

        # -------------------------------------------------
        # CASE 1: NO ROOT MATCH → SAFE PHRASE NEGATIVE
        # -------------------------------------------------
        if not matched_roots:
            final_phrase.add(f'"{term}"')
            continue

        # -------------------------------------------------
        # CASE 2: PURE ROOT (ATOMIC INTENT)
        # Example: "jobs"
        # -------------------------------------------------
        if len(words) == 1:
            final_broad.add(words[0])
            continue

        # -------------------------------------------------
        # CASE 3: MULTI-WORD TERM WITH ROOT
        # DEFAULT SAFE BEHAVIOUR = PHRASE NEGATIVE
        #
        # IMPORTANT:
        # Even if intent is similar, specificity protects
        # commercial overlap.
        # -------------------------------------------------

        final_phrase.add(f'"{term}"')

    # =====================================================
    # 4. OUTPUT STRUCTURE
    # =====================================================

    return {
        "broad_negatives": sorted(final_broad),
        "phrase_negatives": sorted(final_phrase),
        "review_queue": review_output
    }
