import re
from typing import List, Dict


# =====================================================
# NORMALISATION
# =====================================================
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


# =====================================================
# LAYER 6: ROOT NEGATIVE CONSOLIDATION
# =====================================================
def extract_roots_protected(
    negative_terms: List[str],
    review_terms: List[str],
    positive_terms: List[str],
    brand_model: Dict
):

    """
    Layer 6:
    Converts negative search terms into ROOT negative keywords
    ONLY if they do NOT conflict with review/positive intent.
    """

    # =====================================================
    # BUILD PROTECTED VOCAB (NO NEGATION ALLOWED)
    # =====================================================
    protected_tokens = set()

    for t in review_terms + positive_terms:
        for w in normalize(t).split():
            protected_tokens.add(w)

    # =====================================================
    # BRAND-SAFE ROOTS (ALWAYS PROTECTED)
    # =====================================================
    safe_roots = set(
        normalize(x) for x in brand_model.get("safe_roots", [])
    )

    # =====================================================
    # RESULT SET
    # =====================================================
    roots = set()

    # =====================================================
    # EXTRACT FROM NEGATIVES ONLY
    # =====================================================
    for term in negative_terms:

        words = normalize(term).split()

        for w in words:

            # skip brand-protected words
            if w in safe_roots:
                continue

            # CRITICAL RULE:
            # do not extract anything that appears in review/positive context
            if w in protected_tokens:
                continue

            # valid root negative
            roots.add(w)

    return sorted(roots)
