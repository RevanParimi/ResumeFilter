"""Institution + employer canonicalization for the Indian market (S1.4).

Institutions: explicit alias table first (covers tier overrides like IIIT
Hyderabad), then campus patterns for the IIT/IIM/NIT/IIIT systems so the
long tail ("Indian Institute of Technology, Madras") needs no table row.
Tiers are ADVISORY search metadata, not a gate: tier_1/tier_2/None.

Employers: trailing legal tokens (Pvt/Ltd/Inc/...) are stripped, then an
alias table maps to a canonical display name. Unknown orgs return None —
inventing canonicals for unknowns would cause false merges downstream.
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional

from app.candidates.normalize.text import norm_key


class InstitutionMatch(NamedTuple):
    canonical: str
    tier: Optional[str]  # "tier_1" | "tier_2" | None (recognized, untiered)


# canonical display name: (tier, aliases). Indexed via norm_key.
_INSTITUTIONS: dict[str, tuple[Optional[str], tuple[str, ...]]] = {
    "IISc Bangalore": ("tier_1", ("iisc", "indian institute of science", "iisc bangalore", "iisc bengaluru")),
    "BITS Pilani": ("tier_1", ("bits pilani", "bits", "birla institute of technology and science")),
    "IIIT Hyderabad": ("tier_1", ("iiit hyderabad", "iiit-h", "international institute of information technology hyderabad")),
    "ISB Hyderabad": ("tier_1", ("isb", "indian school of business")),
    "Anna University": ("tier_2", ("anna university",)),
    "VTU": ("tier_2", ("vtu", "visvesvaraya technological university")),
    "Jadavpur University": ("tier_2", ("jadavpur university", "jadavpur")),
    "Delhi University": ("tier_2", ("delhi university", "university of delhi")),
    "DTU": ("tier_2", ("dtu", "delhi technological university", "delhi college of engineering", "dce")),
    "Jamia Millia Islamia": ("tier_2", ("jamia millia islamia", "jamia")),
    "VIT Vellore": ("tier_2", ("vit", "vit vellore", "vellore institute of technology")),
    "SRM University": ("tier_2", ("srm", "srm university", "srm institute of science and technology")),
    "MIT Manipal": ("tier_2", ("mit manipal", "manipal institute of technology")),
    "COEP Pune": ("tier_2", ("coep", "college of engineering pune")),
    "PSG College of Technology": ("tier_2", ("psg college of technology", "psg tech")),
    "Amrita Vishwa Vidyapeetham": ("tier_2", ("amrita", "amrita vishwa vidyapeetham", "amrita university")),
    "Osmania University": ("tier_2", ("osmania university", "osmania")),
    "Pune University": ("tier_2", ("pune university", "university of pune", "savitribai phule pune university", "sppu")),
    "IGNOU": (None, ("ignou", "indira gandhi national open university")),
    "LPU": (None, ("lpu", "lovely professional university")),
    "Chandigarh University": (None, ("chandigarh university",)),
}

# Campus patterns run AFTER the alias table (so IIIT Hyderabad keeps tier_1).
_INST_PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"^(?:iit|indian institute of technology)\s+(?P<campus>[a-z][a-z ]*)$"), "IIT {campus}", "tier_1"),
    (re.compile(r"^(?:iim|indian institute of management)\s+(?P<campus>[a-z][a-z ]*)$"), "IIM {campus}", "tier_1"),
    (re.compile(r"^(?:nit|national institute of technology)\s+(?P<campus>[a-z][a-z ]*)$"), "NIT {campus}", "tier_2"),
    (re.compile(r"^(?:iiit|indian institute of information technology)\s+(?P<campus>[a-z][a-z ]*)$"), "IIIT {campus}", "tier_2"),
)

# Campus spellings folded so "NIT Tiruchirappalli" == "NIT Trichy".
_CAMPUS_FIX = {
    "tiruchirappalli": "Trichy",
    "tiruchirapalli": "Trichy",
    "trichy": "Trichy",
}


def _build_inst_index() -> dict[str, InstitutionMatch]:
    index: dict[str, InstitutionMatch] = {}
    for canonical, (tier, aliases) in _INSTITUTIONS.items():
        match = InstitutionMatch(canonical=canonical, tier=tier)
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != match:  # table bug
                raise ValueError(
                    f"institution alias {alias!r} claimed by {existing.canonical} and {canonical}"
                )
            index[key] = match
    return index


_INST_INDEX = _build_inst_index()


def canonicalize_institution(name: str) -> Optional[InstitutionMatch]:
    key = norm_key(name or "")
    if not key:
        return None
    hit = _INST_INDEX.get(key)
    if hit:
        return hit
    for pattern, template, tier in _INST_PATTERNS:
        m = pattern.match(key)
        if m:
            campus = m.group("campus").strip()
            campus = _CAMPUS_FIX.get(campus, campus.title())
            return InstitutionMatch(canonical=template.format(campus=campus), tier=tier)
    return None


# canonical display name: aliases. Indexed via norm_key.
_EMPLOYERS: dict[str, tuple[str, ...]] = {
    "TCS": ("tcs", "tata consultancy services"),
    "Infosys": ("infosys", "infosys technologies"),
    "Infosys BPM": ("infosys bpm",),
    "Wipro": ("wipro", "wipro technologies"),
    "HCL": ("hcl", "hcl technologies", "hcltech"),
    "Tech Mahindra": ("tech mahindra", "techm"),
    "Cognizant": ("cognizant", "cts", "cognizant technology solutions"),
    "Accenture": ("accenture",),
    "Capgemini": ("capgemini",),
    "LTIMindtree": ("ltimindtree", "lti", "mindtree", "l&t infotech", "larsen & toubro infotech"),
    "IBM": ("ibm", "international business machines", "ibm india"),
    "Amazon": ("amazon", "amazon india", "amazon development centre india"),
    "Google": ("google", "google india"),
    "Microsoft": ("microsoft", "microsoft india"),
    "Meta": ("meta", "facebook"),
    "Apple": ("apple",),
    "Netflix": ("netflix",),
    "Adobe": ("adobe", "adobe systems"),
    "Oracle": ("oracle", "oracle india"),
    "SAP": ("sap", "sap labs", "sap labs india"),
    "Salesforce": ("salesforce",),
    "Intuit": ("intuit",),
    "NVIDIA": ("nvidia",),
    "Uber": ("uber",),
    "Walmart Global Tech": ("walmart", "walmart global tech", "walmart labs"),
    "Flipkart": ("flipkart",),
    "Myntra": ("myntra",),
    "Paytm": ("paytm", "one97", "one97 communications"),
    "PhonePe": ("phonepe",),
    "Razorpay": ("razorpay",),
    "Zomato": ("zomato",),
    "Swiggy": ("swiggy",),
    "Ola": ("ola", "ola cabs", "ani technologies"),
    "Zoho": ("zoho",),
    "Freshworks": ("freshworks", "freshdesk"),
    "Zerodha": ("zerodha",),
    "CRED": ("cred", "dreamplug technologies"),
    "Meesho": ("meesho",),
    "Reliance Jio": ("jio", "reliance jio", "jio platforms"),
    "Deloitte": ("deloitte", "deloitte india", "deloitte usi"),
    "EY": ("ey", "ernst & young", "ernst and young"),
    "KPMG": ("kpmg",),
    "PwC": ("pwc", "pricewaterhousecoopers"),
    "JPMorgan Chase": ("jpmorgan", "jp morgan", "jpmorgan chase", "jpmc"),
    "Goldman Sachs": ("goldman sachs",),
    "Morgan Stanley": ("morgan stanley",),
    "Barclays": ("barclays",),
    "Samsung R&D": ("samsung", "samsung r&d", "samsung electronics"),
    "Qualcomm": ("qualcomm",),
    "Intel": ("intel",),
    "Cisco": ("cisco", "cisco systems"),
    "Dell": ("dell", "dell technologies", "emc", "dell emc"),
    "VMware": ("vmware",),
    "Atlassian": ("atlassian",),
    "ServiceNow": ("servicenow",),
    "Nagarro": ("nagarro",),
    "Persistent Systems": ("persistent", "persistent systems"),
    "Mphasis": ("mphasis",),
    "Hexaware": ("hexaware", "hexaware technologies"),
    "Coforge": ("coforge", "niit technologies"),
    "Genpact": ("genpact",),
}

_LEGAL_TOKENS = {
    "pvt", "private", "ltd", "limited", "llp", "inc",
    "co", "corp", "corporation", "company", "india",
}


def _build_emp_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for canonical, aliases in _EMPLOYERS.items():
        for alias in aliases:
            key = norm_key(alias)
            existing = index.get(key)
            if existing is not None and existing != canonical:  # table bug
                raise ValueError(
                    f"employer alias {alias!r} claimed by {existing} and {canonical}"
                )
            index[key] = canonical
    return index


_EMP_INDEX = _build_emp_index()


def canonicalize_employer(name: str) -> Optional[str]:
    words = norm_key(name or "").split()
    while words:
        hit = _EMP_INDEX.get(" ".join(words))
        if hit:
            return hit
        if words[-1] in _LEGAL_TOKENS:
            words.pop()  # "wipro pvt ltd" -> "wipro pvt" -> "wipro"
        else:
            return None
    return None
