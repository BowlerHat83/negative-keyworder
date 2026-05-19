import re

# =====================================================
# NORMALISE
# =====================================================

def normalize(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


# =====================================================
# INTENT ROOT EXTRACTION (CONTROLLED)
# =====================================================

def extract_intent_roots(negative_terms, protected_roots):

    """
    Extract ONLY true intent triggers (not random words).
    """

    intent_vocab = {
        "job", "jobs", "career", "careers",
        "salary", "salaries",
        "free", "cheap",
        "template", "templates",
        "download",
        "how", "what", "why",
        "tutorial", "guide",
        "pdf",
        "reddit", "youtube"
    }

    roots = set()

    for term in negative_terms:

        words = normalize(term).split()

        for w in words:

            if w in protected_roots:
                continue

            if w in intent_vocab:
                roots.add(w)

    return sorted(roots)


# =====================================================
# ROOT DEDUPLICATION
# =====================================================

def dedupe(roots):
    return sorted(set(normalize(r) for r in roots if r))


# =====================================================
# SAFE EXPANSION ENGINE (CRITICAL SAFETY LAYER)
# =====================================================

def expand_roots_safe(roots, brand_model):

    """
    Expands ONLY if it does NOT conflict with brand context.

    Example:
    - job → jobs (safe)
    - salary → salaries (safe)
    - BUT no semantic expansion beyond morphology
    """

    expanded = set()

    # brand sensitivity signals
    high_risk_context = set([
        normalize(x)
        for x in brand_model.get("risk_terms", [])
    ])

    for r in roots:

        r = normalize(r)

        expanded.add(r)

        # -------------------------
        # SAFE MORPHOLOGICAL EXPANSION ONLY
        # -------------------------

        if r == "job":
            expanded.add("jobs")

        elif r == "career":
            expanded.add("careers")

        elif r == "salary":
            expanded.add("salaries")

        elif r == "template":
            expanded.add("templates")

        elif r == "download":
            expanded.add("downloads")

        # -------------------------
        # CONDITIONAL EXPANSION RULE
        # -------------------------

        # Only expand if not flagged as risky context
        if r in high_risk_context:
            continue

    return sorted(expanded)


# =====================================================
# GOOGLE ADS FORMATTER
# =====================================================

def format_google_ads(terms):

    """
    Converts to Google Ads-compatible negatives.
    """

    output = []

    for t in terms:

        t = t.strip()

        if not t:
            continue

        # phrase match for multi-word terms
        if " " in t:
            output.append(f'"{t}"')
        else:
            output.append(t)

    return sorted(set(output))


# =====================================================
# MAIN PIPELINE
# =====================================================

def build_layer7_output(negative_terms, brand_model):

    """
    Full Layer 7 pipeline
    """

    # =========================
    # PROTECTED ROOTS
    # =========================

    protected_roots = set([
        normalize(x)
        for x in brand_model.get("safe_roots", [])
    ])

    # =========================
    # STEP 1 — ROOT EXTRACTION
    # =========================

    roots = extract_intent_roots(
        negative_terms,
        protected_roots
    )

    roots = dedupe(roots)

    # =========================
    # STEP 2 — SAFE EXPANSION
    # =========================

    expanded = expand_roots_safe(
        roots,
        brand_model
    )

    # =========================
    # STEP 3 — MERGE
    # =========================

    merged = negative_terms + expanded

    # =========================
    # STEP 4 — FINAL FORMAT
    # =========================

    final = format_google_ads(merged)

    return {
        "roots": roots,
        "expanded": expanded,
        "final": final
    }
