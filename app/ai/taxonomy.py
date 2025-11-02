# app/ai/taxonomy.py
#
# Goal:
# - Local, cheap, "fast pass" categorization for muni RFPs/RFQs/ITBs
# - Human-readable category names (no snake_case)
# - Backward-compatible shims for old snake_case names
# - Easy to extend / tweak when you see new local patterns
#
# Usage (quick):
#     from app.ai.taxonomy import fast_category_from_title
#     cat = fast_category_from_title("RFP: SWACO Transfer Station Roofing and Siding Improvements")
#     # -> "Construction"
#
# Then you can store that in opportunities.ai_category (or whatever you called it)

from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 1. MAIN CATEGORIES (human readable)
# ---------------------------------------------------------------------------
# Note: keep these names stable — this is what you’ll show in the UI and save
# in the DB going forward.
#
# These are tailored to what you’re scraping right now:
#   - Columbus-area municipalities
#   - transit (COTA)
#   - county / SWACO / CRAA
#   - school districts
#   - parks / metro parks
#   - water/sewer/storm items
#
# If you point this at a new agency, just add their common phrases to the lists.

BASE_CATEGORIES: Dict[str, List[str]] = {
    # 1. Construction / Capital / Vertical / Horizontal
    "Construction": [
        # generic
        "construction",
        "capital improvement",
        "capital improvements",
        "improvement project",
        "renovation",
        "building renovation",
        "interior renovation",
        "facility renovation",
        "tenant improvement",
        "fit-out",
        "fit out",
        "remodel",
        "build-out",
        "build out",
        "addition",
        "retrofit",
        "structural repair",
        "structural rehabilitation",
        "restoration",
        # site / civil / roadway
        "paving",
        "pavement",
        "mill and fill",
        "resurfacing",
        "street improvement",
        "street improvements",
        "roadway",
        "road improvements",
        "road reconstruction",
        "curb",
        "gutter",
        "sidewalk",
        "concrete work",
        "concrete replacement",
        "parking lot",
        "parking improvements",
        "alley improvements",
        # water / sewer / storm as CONSTRUCTION (not O&M)
        "waterline replacement",
        "water line replacement",
        "water main",
        "water main replacement",
        "sanitary sewer",
        "sanitary improvements",
        "wastewater improvements",
        "wwtp improvements",
        "pump station improvements",
        "lift station improvements",
        "force main",
        "stormwater improvement",
        "storm water improvement",
        "storm sewer",
        "culvert replacement",
        "lining contract",
        "sewer lining",
        # vertical / building systems
        "roof replacement",
        "roof rehabilitation",
        "roofing project",
        "elevator improvements",
        "hvac replacement",
        "mechanical improvements",
        "boiler replacement",
        "chiller replacement",
        # delivery methods
        "cmar",
        "construction manager at risk",
        "cm-at-risk",
        "cm at risk",
        "design-build",
        "design build",
        "design build services",
        # transit construction / brt
        "bus rapid transit",
        "brt",
        "corridor improvements",
        "streetscape",
        "streetscape improvements",
        # parks-type but construction in nature
        "trail construction",
        "path construction",
        "shelter construction",
        "restroom building",
    ],

    # 2. Utilities, Water, Sewer, Storm, Solid Waste INFRASTRUCTURE (O&M-ish)
    #    (separate from construction above so you can filter ops vs project)
    "Utilities / Water / Sewer / Storm": [
        "water treatment",
        "wastewater treatment",
        "wwtp",
        "lift station",
        "pump station",
        "odor control",
        "sludge hauling",
        "biosolids",
        "lab analysis",
        "water testing",
        "sewer jetting",
        "sewer cleaning",
        "cctv inspection",
        "leak detection",
        "hydrant replacement",
        "meter replacement",
        "stormwater services",
        "storm water services",
        "backflow testing",
        "manhole rehab",
        "pipe bursting",
        "sewer repair",
        "sanitary maintenance",
    ],

    # 3. Solid Waste / Recycling / Environmental (SWACO-style)
    "Solid Waste / Recycling / Environmental": [
        "solid waste",
        "waste collection",
        "trash collection",
        "refuse collection",
        "recycling services",
        "yard waste",
        "household hazardous waste",
        "transfer station",
        "landfill services",
        "leachate hauling",
        "composting",
        "environmental consulting",
        "hazmat",
        "hazardous materials",
        "roll-off containers",
    ],

    # 4. Information Technology & Cybersecurity
    "Information Technology": [
        "software",
        "software as a service",
        "saas",
        "paas",
        "cloud solution",
        "it services",
        "information technology",
        "network",
        "networking",
        "firewall",
        "endpoint",
        "cyber",
        "cybersecurity",
        "security operations",
        "soc",
        "mfa",
        "idm",
        "identity management",
        "email security",
        "website redesign",
        "website design",
        "web redesign",
        "cms",
        "content management system",
        "portal",
        "data platform",
        "centralized data platform",
        "data warehouse",
        "business intelligence",
        "bi platform",
        "analytics platform",
        "gis",
        "arcgis",
        "esri",
        "erp",
        "crm",
        "hris",
        "licenses and support",
        "software maintenance",
        "managed services",
        "help desk",
    ],

    # 5. Professional Services (AEC, planning, studies, marketing, comms)
    "Professional Services": [
        "consultant",
        "consulting",
        "engineering services",
        "architectural services",
        "a/e services",
        "planning",
        "master plan",
        "planning services",
        "feasibility study",
        "study",
        "design services",
        "design consultant",
        "surveying",
        "right-of-way services",
        "row acquisition",
        "appraisal services",
        "property acquisition",
        # business / comms
        "marketing",
        "advertising",
        "public relations",
        "branding",
        "community engagement",
        "outreach services",
        # compliance / analysis
        "availability study",
        "disparity study",
        "cost allocation study",
        "rate study",
        # property mgmt done as a pro service
        "property management services",
        "real estate services",
    ],

    # 6. Staffing, Temporary Labor, HR Outsourcing
    "Staffing / Human Resources": [
        "temporary personnel",
        "temporary personnel services",
        "temporary staffing",
        "temp staffing",
        "staff augmentation",
        "personnel services",
        "staffing services",
        "recruitment services",
        "recruiting services",
        "executive search",
        "background checks",
        "employee assistance",
        "benefits administration",
        "hr services",
        "payroll services",
    ],

    # 7. Facilities, Janitorial, Building Maintenance, Grounds
    "Facilities / Janitorial / Grounds": [
        "janitorial",
        "cleaning",
        "custodial",
        "custodial services",
        "facility maintenance",
        "building maintenance",
        "preventive maintenance",
        "pm services",
        "hvac maintenance",
        "mechanical maintenance",
        "elevator maintenance",
        "fire alarm testing",
        "fire suppression",
        "security system maintenance",
        "pest control",
        "grounds maintenance",
        "landscaping",
        "mowing",
        "snow removal",
        "ice removal",
        "lawn care",
        "property maintenance",
    ],

    # 8. Parks, Recreation, Trails, Athletic Fields (non-construction flavor)
    "Parks / Recreation / Trails": [
        "park",
        "playground",
        "play equipment",
        "trail",
        "greenway",
        "metro parks",
        "athletic field",
        "sports field",
        "ballfield",
        "recreation program",
        "recreation services",
        "tree planting",
        "tree removal",
        "site amenities",
    ],

    # 9. Transportation, Fleet, Transit, Vehicles, Buses
    "Transportation / Fleet / Transit": [
        "transit",
        "bus",
        "paratransit",
        "demand-response",
        "fleet",
        "fleet vehicles",
        "vehicle purchase",
        "vehicles",
        "police vehicles",
        "fire apparatus",
        "ambulance",
        "snow plow truck",
        "upfit",
        "lift upfit",
        "vehicle upfitting",
        "rolling stock",
        "cng",
        "natural gas coaches",
        "heavy duty transit coaches",
        "tsi",  # COTA transit supportive infrastructure
    ],

    # 10. Finance, Administration, Insurance, Audits
    "Finance / Administration / Insurance": [
        "audit",
        "financial audit",
        "actuarial",
        "insurance",
        "benefits",
        "third party administrator",
        "tpa services",
        "grant administration",
        "program administration",
        "claims administration",
        "debt advisory",
        "arbitrage",
        "banking services",
        "merchant services",
    ],

    # 11. Public Safety, Fire, EMS, Security
    "Public Safety / Fire / EMS": [
        "public safety",
        "police",
        "law enforcement",
        "in-car video",
        "body-worn camera",
        "dispatch",
        "cad / rms",
        "records management system",
        "evidence management",
        "fire",
        "ems",
        "ambulance",
        "turnout gear",
        "scba",
        "radio system",
        "p25",
        "emergency communications",
    ],

    # 12. Training, Education, Outreach
    "Training / Education": [
        "training",
        "training services",
        "professional development",
        "compliance course",
        "safety training",
        "osha training",
        "diversity training",
        "disability empathy training",
        "public education campaign",
        "school curriculum",
    ],

    # 13. Printing, Marketing Materials, Mail, Creative
    "Printing / Marketing / Communications": [
        "printing",
        "print services",
        "mailing services",
        "direct mail",
        "graphic design",
        "creative services",
        "marketing materials",
        "promotional products",
    ],

    # 14. Commodities, Supplies, MRO, Equipment (non-IT)
    "Supplies / MRO / Equipment": [
        "janitorial supplies",
        "office supplies",
        "lab supplies",
        "shop supplies",
        "pavement marking materials",
        "thermoplastic",
        "glass beads",
        "equipment parts",
        "pump parts",
        "valves",
        "meters",
        "filters",
        "safety equipment",
        "ppe",
        "hand tools",
        "power tools",
        "furniture",
        "commercial furniture upholstery",
        "building materials",
        "aggregates",
        "salt",
        "calcium chloride",
    ],

    # 15. Food, Vending, Concessions (for parks / schools / transit)
    "Food / Vending / Concessions": [
        "food service",
        "cafeteria services",
        "catering",
        "vending services",
        "concession services",
        "snack bar",
    ],

    # 16. Real Estate, Property & Asset Management
    "Real Estate / Property Management": [
        "property management",
        "real estate services",
        "appraisal",
        "right-of-way acquisition",
        "lease management",
        "facility leasing",
    ],

    # 17. Grants, Social Programs, Community Development
    "Grants / Community Programs": [
        "grant program",
        "grant administration",
        "community development",
        "housing services",
        "youth program",
        "after-school program",
        "violence prevention",
        "workforce development",
    ],

    # 18. Catch-all
    "Other / Miscellaneous": [],
}

# ---------------------------------------------------------------------------
# 2. LEGACY → NEW NAME MAP
#    so old code that used "construction" still works
# ---------------------------------------------------------------------------
LEGACY_CATEGORY_ALIASES: Dict[str, str] = {
    "construction": "Construction",
    "it": "Information Technology",
    "professional_services": "Professional Services",
    "staffing_hr": "Staffing / Human Resources",
    "facilities_janitorial": "Facilities / Janitorial / Grounds",
    "transportation": "Transportation / Fleet / Transit",
    "parks_grounds": "Parks / Recreation / Trails",
    "finance_admin": "Finance / Administration / Insurance",
    "supplies_mro": "Supplies / MRO / Equipment",
    "training": "Training / Education",
    "other": "Other / Miscellaneous",
}

# ---------------------------------------------------------------------------
# 3. FAST CLASSIFIER
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    return (title or "").strip().lower()


def _strong_phrases() -> List[tuple[str, str]]:
    """
    Phrases we want to match BEFORE normal keyword matching.
    Ordered from most specific to least.
    """
    return [
        ("construction manager at risk", "Construction"),
        ("cmar", "Construction"),
        ("design-build", "Construction"),
        ("bus rapid transit", "Construction"),
        ("transfer station", "Solid Waste / Recycling / Environmental"),
        ("landfill", "Solid Waste / Recycling / Environmental"),
        ("website redesign", "Information Technology"),
        ("body-worn camera", "Public Safety / Fire / EMS"),
        ("in-car video", "Public Safety / Fire / EMS"),
        ("snow removal", "Facilities / Janitorial / Grounds"),
        ("janitorial services", "Facilities / Janitorial / Grounds"),
        ("temporary staffing", "Staffing / Human Resources"),
        ("property management services", "Real Estate / Property Management"),
    ]


def fast_category_from_title(title: str) -> str:
    """
    Very fast, no-LLM categorization.
    Returns a nice, human-readable category name.
    """
    t = _normalize_title(title)

    if not t:
        return "Other / Miscellaneous"

    # 1) strong phrases first
    for phrase, cat in _strong_phrases():
        if phrase in t:
            return cat

    # 2) normal keyword scanning
    for cat_name, keywords in BASE_CATEGORIES.items():
        if not keywords:
            continue
        for kw in keywords:
            kw_l = kw.lower()
            if kw_l and kw_l in t:
                return cat_name

    # 3) fallback
    return "Other / Miscellaneous"


def normalize_category_name(name: str) -> str:
    """
    If something in the pipeline still passes 'construction' (snake case),
    we'll map it to 'Construction'. If it's already good, return as-is.
    """
    if not name:
        return "Other / Miscellaneous"

    n = name.strip()

    # exact match (pretty name)
    if n in BASE_CATEGORIES:
        return n

    # lowercase snake/slug
    key = n.lower().replace(" ", "_").replace("-", "_")
    if key in LEGACY_CATEGORY_ALIASES:
        return LEGACY_CATEGORY_ALIASES[key]

    # try lowercase direct
    if n.lower() in LEGACY_CATEGORY_ALIASES:
        return LEGACY_CATEGORY_ALIASES[n.lower()]

    return "Other / Miscellaneous"


# ---------------------------------------------------------------------------
# 4. Small self-test (you can run this file directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    samples = [
        "RFP: SWACO Transfer Station Roofing and Siding Improvements",
        "Bid: Janitorial Services – City Hall and Service Center",
        "RFQ: Website Redesign and CMS Migration",
        "RFP: Transit Supportive Infrastructure (TSI) – COTA",
        "ITB: Asphalt Resurfacing Program – 2026",
        "RFP: Temporary Personnel Services",
        "RFP: Centralized Data Platform and SaaS",
        "RFP: Tree Removal and Stump Grinding",
        "RFP: Construction Manager at Risk for BRT Corridor",
        "RFP: Financial Audit Services",
        "RFP: Household Hazardous Waste Collection Program",
        "RFP: Body-Worn Camera System for Police Department",
        "RFP: Parking Lot Snow Removal",
        "RFP: Food and Vending Services for Parks",
        "RFQ: Appraisal and ROW Acquisition",
    ]
    for s in samples:
        print(s, "->", fast_category_from_title(s))
