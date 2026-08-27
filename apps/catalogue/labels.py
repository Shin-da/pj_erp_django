"""Display labels for legacy jewellery sub-category codes.

`tblsub_category_master.sub_category` stores the short code as the name
(ER, RN, NL, …). Staff know those codes; the dashboard also shows a
plain-language label. Stored values are never rewritten.
"""

SUBCATEGORY_LABELS = {
    "ER": "Earrings",
    "RN": "Rings",
    "NL": "Necklaces",
    "BR": "Bracelets",
    "PND": "Pendants",
    "BNG": "Bangles",
    "CHN": "Chains",
    "SET": "Sets",
    "ANK": "Anklets",
    "NAIL": "Nail",
    "CHKR": "Chokers",
    "CRW": "Crowns",
    "CHRM": "Charms",
    "ST": "Studs",
    "BRCH": "Brooches",
    "TRY": "Trays",
    "RNBX": "Ring boxes",
    "GLDBR": "Gold bars",
    "LSLGDIA": "Loose lab-grown diamond",
}


def subcategory_label(code):
    if not code:
        return ""
    name = SUBCATEGORY_LABELS.get(code)
    if name and name.upper() != code.upper():
        return f"{name} ({code})"
    return code
