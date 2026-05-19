import re

# =====================================================
# NORMALISE
# =====================================================

def normalize(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


# =====================================================
# ROOT EXTRACTION WITH PROTECTION LAYER
# =====================================================

def extract_roots_protected(
    negative_terms,
    review_terms,
    positive_terms,
    brand_model
):

    """
    Extract roots ONLY from negatives,
    while ensuring we do NOT destroy valid intent patterns
    found in review/positive terms.
    """

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

    # =========================
    # PROTECTION SET
    # =========================

    protected_terms = set(
        normalize(t)
        for t in (review_terms + positive_terms)
    )

    protected_roots = set(
        normalize(x)
        for x in brand_model.get("safe_roots", [])
    )

    roots = set()

    # =========================
    # ROOT EXTRACTION LOOP
    # =========================

    for term in negative_terms:

        t = normalize(term)

        # skip if term appears in review/positive context
        if t in protected_terms:
            continue

        words = t.split()

        for w in words:

            # protect brand-safe roots
            if w in protected_roots:
                continue

            if w in intent_vocab:
                roots.add(w)

    return sorted(roots)
