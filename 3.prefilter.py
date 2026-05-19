import re

# =====================================================
# NORMALISATION
# =====================================================

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


# =====================================================
# CONTEXTUAL PREFILTER ENGINE
# =====================================================

def contextual_prefilter(terms: list, brand: dict):

    """
    Removes obviously irrelevant terms using BRAND CONTEXT.
    Keeps ambiguous terms for AI classification.
    """

    auto_negative = []
    remaining = []

    # =========================
    # BRAND SIGNALS
    # =========================

    low_value_signals = set([
        normalize(x)
        for x in brand.get("low_value_intents", [])
    ])

    safe_roots = set([
        normalize(x)
        for x in brand.get("safe_roots", [])
    ])

    product_states = set([
        normalize(x)
        for x in brand.get("product_state_context", [])
    ])

    # =========================
    # RULE 1: LOW VALUE INTENT MATCH
    # =========================

    for term in terms:

        t = normalize(term)

        matched = False

        for signal in low_value_signals:
            if signal and signal in t:
                auto_negative.append(term)
                matched = True
                break

        if matched:
            continue

        # =========================
        # RULE 2: SAFE ROOT PROTECTION
        # (DO NOT FILTER THESE)
        # =========================

        for root in safe_roots:
            if root and root in t:
                remaining.append(term)
                matched = True
                break

        if matched:
            continue

        # =========================
        # RULE 3: PRODUCT STATE CONTEXT
        # (DO NOT AUTO-NEGATIVE THESE)
        # =========================

        for state in product_states:
            if state and state in t:
                remaining.append(term)
                matched = True
                break

        if matched:
            continue

        # =========================
        # RULE 4: DEFAULT BEHAVIOUR
        # (PASS TO AI FOR SAFETY)
        # =========================

        remaining.append(term)

    return auto_negative, remaining
