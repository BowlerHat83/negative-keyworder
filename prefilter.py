import re
from typing import List, Tuple, Dict


# =====================================================
# NORMALISATION
# =====================================================
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


# =====================================================
# SCORE-BASED PREFILTER (BRAND CONTEXT DRIVEN)
# =====================================================
def contextual_prefilter(terms: List[str], brand_model: Dict) -> Tuple[List[str], List[str]]:

    """
    Layer 4 Prefilter Engine

    Input:
        terms -> raw search terms
        brand_model -> Layer 3 output

    Output:
        auto_negative -> safe removals
        remaining -> must go to LLM
    """

    auto_negative = []
    remaining = []

    # =====================================================
    # BRAND CONTEXT SIGNALS (FROM LAYER 3 ONLY)
    # =====================================================
    positioning = brand_model.get("positioning", "unknown")
    price_positioning = brand_model.get("price_positioning", "unknown")
    intent_profile = brand_model.get("intent_profile", "unknown")

    safe_roots = set(normalize(x) for x in brand_model.get("safe_roots", []))
    low_value_intents = set(normalize(x) for x in brand_model.get("low_value_intents", []))
    risk_terms = set(normalize(x) for x in brand_model.get("risk_terms", []))
    bias_rules = brand_model.get("negative_bias_rules", [])

    # =====================================================
    # RULE ENGINE (CONTEXTUAL, NOT HARDCODED FILTERING)
    # =====================================================

    def violates_low_value(term: str) -> bool:
        """Check against learned low-value intents"""
        return any(sig in term for sig in low_value_intents)

    def safe_root_match(term: str) -> bool:
        """Protect brand-critical language"""
        return any(root in term for root in safe_roots)

    def risk_context(term: str) -> bool:
        """Do NOT auto-remove — send to LLM"""
        return any(risk in term for risk in risk_terms)

    # =====================================================
    # BIAS RULE EVALUATION (DYNAMIC)
    # =====================================================
    def apply_bias_rules(term: str) -> bool:
        """
        Returns True if term is clearly negative based on brand rules
        """

        for rule in bias_rules:
            rule = normalize(rule)

            # simple semantic rule interpretation
            if "cheap" in rule and "luxury" in positioning:
                if "cheap" in term:
                    return True

            if "free" in rule and intent_profile == "commercial":
                if "free" in term:
                    return True

            if "used" in rule and "new" in positioning:
                if "used" in term:
                    return True

        return False

    # =====================================================
    # MAIN LOOP
    # =====================================================
    for term in terms:

        t = normalize(term)

        # -------------------------------------------------
        # 1. PROTECT SAFE ROOTS (NEVER REMOVE)
        # -------------------------------------------------
        if safe_root_match(t):
            remaining.append(term)
            continue

        # -------------------------------------------------
        # 2. RISK TERMS → ALWAYS PASS TO LLM
        # -------------------------------------------------
        if risk_context(t):
            remaining.append(term)
            continue

        # -------------------------------------------------
        # 3. LOW VALUE INTENT CHECK
        # -------------------------------------------------
        if violates_low_value(t):
            auto_negative.append(term)
            continue

        # -------------------------------------------------
        # 4. BRAND BIAS RULES
        # -------------------------------------------------
        if apply_bias_rules(t):
            auto_negative.append(term)
            continue

        # -------------------------------------------------
        # 5. DEFAULT → LET AI DECIDE
        # -------------------------------------------------
        remaining.append(term)

    return auto_negative, remaining
