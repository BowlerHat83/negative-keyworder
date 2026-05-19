import re
from typing import List, Dict


# =====================================================
# NORMALISATION
# =====================================================
def normalize(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


# =====================================================
# LAYER 6: ROOT NEGATIVE EXTRACTION
# =====================================================
def extract_roots_protected(
    negative_terms: List[str],
    review_terms: List[str],
    positive_terms: List[str],
    brand_model: Dict
) -> List[str]:

    """
    Extract root negatives ONLY from negative terms.

    HARD RULES:
    - NEVER extract roots from review/positive terms
    - NEVER extract brand-safe roots
    - ONLY extract intent-bearing tokens from negatives
    """

    # -------------------------
    # INTENT VOCAB (safe abstraction layer)
    # -------------------------
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

    # -------------------------
    # PROTECTION SETS
    # -------------------------

    protected_terms = set(
        normalize(t)
        for t in (review_terms + positive_terms)
        if t
    )

    protected_roots = set(
        normalize(x)
        for x in brand_model.get("safe_roots", [])
        if x
    )

    # -------------------------
    # ROOT EXTRACTION
    # -------------------------
    roots = set()

    for term in negative_terms:

        if not term:
            continue

        t = normalize(term)

        # NEVER touch anything that overlaps review/positive context
        if t in protected_terms:
            continue

        words = t.split()

        for w in words:

            # protect brand-defined safe roots
            if w in protected_roots:
                continue

            # extract only intent-driven tokens
            if w in intent_vocab:
                roots.add(w)

    return sorted(roots)
