# app/ai/taxonomy.py
#
# This is the "fast pass" layer. LLM will still fix stuff it can't match,
# but this should now get 70–80% of muni-style titles by itself.

BASE_CATEGORIES = {
    # 1. Construction / vertical / horizontal / CMaR / BRT
    "construction": [
        # generic
        "construction", "capital improvements", "improvement project",
        "renovation", "building renovation", "interior renovation",
        "tenant improvements", "fit-out", "fit out",
        # site / civil / paving
        "paving", "pavement", "resurfacing", "mill and fill",
        "street improvement", "street improvements",
        "roadway", "road improvements", "road reconstruction",
        "sidewalk", "curb", "gutter", "concrete",
        "parking lot", "parking improvements",
        # water / sewer / storm (still construction flavor)
        "waterline", "water line", "water main", "water main replacement",
        "sewer", "sanitary sewer", "wastewater", "wwtp",
        "pump station", "lift station", "force main",
        "stormwater", "storm water",
        "lining contract", "annual lining", "sewer lining",
        # dam / plant
        "dam improvements", "hoover dam", "tunnel repair",
        "treatment plant", "water plant", "water treatment plant",
        # delivery methods
        "cmar", "cma r", "cm-at-risk", "cm at risk", "construction manager at risk",
        "design-build", "design build",
        # transit construction
        "bus rapid transit", "brt", "corridor improvements",
        # vertical
        "elevator improvements", "roof", "roofing", "hvac",
    ],

    # 2. IT / Data / SaaS / Cyber
    "it": [
        "software", "it", "information technology",
        "network", "networking", "infrastructure",
        "website", "web site", "web redesign", "cms",
        "cyber", "cybersecurity", "security", "endpoint",
        "portal", "saas", "paas",
        "erp", "crm", "hris",
        "autodesk", "licenses", "support & maintenance",
        "data platform", "centralized data platform",
        "business intelligence", "bi platform", "analytics platform",
        "technology support services",
    ],

    # 3. Professional / consulting / planning / studies
    "professional_services": [
        "consultant", "consulting",
        "engineering", "architectural", "a/e",
        "planning", "master plan", "feasibility study", "study",
        "design services", "design consultant",
        "property management",
        "real estate services",
        "appraisal",
        "marketing", "advertising", "public relations", "branding",
        "community engagement", "availability study", "disparity study",
        "strategic support", "strategy support",
    ],

    # 4. Staffing / temp labor / HR services (NEW)
    "staffing_hr": [
        "temporary personnel", "temporary personnel services",
        "temporary staffing", "temp staffing", "staff augmentation",
        "personnel services", "staffing services",
        "recruitment services", "recruiting services",
        "administrative staffing",
    ],

    # 5. Facilities, janitorial, grounds
    "facilities_janitorial": [
        "janitorial", "cleaning", "custodial",
        "maintenance services", "facility maintenance",
        "landscaping", "mowing", "grounds",
        "snow removal", "ice removal",
        "pest control",
        "property maintenance", "property maint.", "property maint",
        "lawn care",
    ],

    # 6. Transportation / vehicles / coaches / paratransit
    "transportation": [
        "transit", "bus", "fleet",
        "vehicle", "vehicles",
        "paratransit",
        "cng", "natural gas coaches",
        "transit coaches", "heavy duty transit coaches",
        "tsi", "cota",
        "rolling stock",
    ],

    # 7. Parks / recreation / athletic / trails
    "parks_grounds": [
        "park", "playground",
        "trail", "greenway",
        "metro parks",
        "athletic field", "sports field", "ballfield", "ball field",
        "recreation improvements",
        "site amenities",
    ],

    # 8. Finance / admin / insurance / benefits
    "finance_admin": [
        "audit", "actuarial",
        "insurance", "benefits",
        "payroll",
        "hr services",
        "grant administration", "program administration",
    ],

    # 9. Supplies / MRO / equipment (non-IT) (NEW)
    "supplies_mro": [
        "janitorial supplies", "office supplies",
        "absorbents", "spill containment",
        "thermoplastic", "glass beads", "pavement marking materials",
        "lab supplies", "autoclave service", "analyzer service",
        "lift upfit", "bucket lift", "upfit",
        "furniture upholstery", "commercial furniture upholstery",
        "equipment parts", "seals & gaskets", "westech",
    ],

    # 10. Training / compliance (NEW)
    "training": [
        "training", "training services", "compliance course",
        "disability empathy training", "safety training",
    ],

    # Fallback
    "other": [],
}
