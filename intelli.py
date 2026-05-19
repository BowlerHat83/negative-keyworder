import google.generativeai as genai
import json
import re

model = genai.GenerativeModel("gemini-2.5-flash")

def safe_generate(prompt):
    try:
        return model.generate_content(prompt).text.strip()
    except:
        return None

def extract_json(text):
    try:
        return json.loads(text)
    except:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                return None
    return None

def build_brand_model(page_text, target_keywords, campaign_type):

    prompt = f"""
Return ONLY JSON.

{
  "business_type": "",
  "positioning": "",
  "price_positioning": "",
  "product_state_context": [],
  "core_offerings": [],
  "safe_roots": [],
  "commercial_intents": [],
  "low_value_intents": [],
  "risk_terms": []
}

Rules:
- positioning defines how words like cheap/luxury are interpreted
- product_state_context includes new/used/refurbished
- ads assume commercial intent first

Campaign: {campaign_type}
Keywords: {target_keywords}

Page:
{page_text[:5000]}
"""

    res = safe_generate(prompt)
    data = extract_json(res) if res else None

    return data or {
        "business_type": "unknown",
        "positioning": "unknown",
        "price_positioning": "unknown",
        "product_state_context": [],
        "core_offerings": [],
        "safe_roots": [],
        "commercial_intents": [],
        "low_value_intents": [],
        "risk_terms": []
    }
