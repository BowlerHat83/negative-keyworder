def contextual_prefilter(terms, brand):

    low_value = set([t.lower() for t in brand.get("low_value_intents", [])])

    auto_negative = []
    remaining = []

    for t in terms:

        matched = False

        for lv in low_value:
            if lv in t:
                auto_negative.append(t)
                matched = True
                break

        if not matched:
            remaining.append(t)

    return auto_negative, remaining
