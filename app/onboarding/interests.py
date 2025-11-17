from __future__ import annotations

from typing import Dict, List

DEFAULT_INTEREST_KEY = "everything"

# Centralized options (display label + backend mapping)
INTEREST_CONFIG: Dict[str, Dict[str, object]] = {
    "construction": {
        "label": "Construction & Renovation",
        "categories": [
            "Construction",
            "Utilities / Water / Sewer / Storm",
            "Transportation / Fleet / Transit",
        ],
        "tags": [
            "construction",
            "renovation",
            "roof",
            "paving",
            "cmar",
            "design build",
        ],
        "default_agencies": [
            "City of Columbus",
            "City of Gahanna",
            "Delaware County",
        ],
        "default_frequency": "daily",
    },
    "professional_services": {
        "label": "Professional Services (A/E/Consulting)",
        "categories": [
            "Professional Services",
            "Finance / Administration / Insurance",
        ],
        "tags": [
            "architect",
            "engineering",
            "study",
            "consulting",
            "design services",
        ],
        "default_agencies": [
            "City of Columbus",
            "City of Westerville",
            "Mid-Ohio Regional Planning Commission (MORPC)",
        ],
        "default_frequency": "weekly",
    },
    "it_technology": {
        "label": "IT & Technology",
        "categories": [
            "Information Technology",
        ],
        "tags": [
            "software",
            "network",
            "cyber",
            "hardware",
        ],
        "default_agencies": [
            "Central Ohio Transit Authority (COTA)",
            "City of Columbus",
            "Columbus Metropolitan Library",
        ],
        "default_frequency": "daily",
    },
    "facility_ops": {
        "label": "Facility Maintenance & Operations",
        "categories": [
            "Facilities / Janitorial / Grounds",
            "Utilities / Water / Sewer / Storm",
        ],
        "tags": [
            "janitorial",
            "landscaping",
            "maintenance",
            "facility",
            "operations",
        ],
        "default_agencies": [
            "City of Grove City",
            "Columbus and Franklin County Metro Parks",
            "Solid Waste Authority of Central Ohio (SWACO)",
        ],
        "default_frequency": "weekly",
    },
    "supplies_equipment": {
        "label": "Supplies & Equipment",
        "categories": [
            "Supplies / MRO / Equipment",
        ],
        "tags": [
            "equipment",
            "supplies",
            "materials",
            "fleet",
        ],
        "default_agencies": [
            "Franklin County, Ohio",
            "City of Columbus",
            "Columbus Regional Airport Authority (CRAA)",
        ],
        "default_frequency": "weekly",
    },
    DEFAULT_INTEREST_KEY: {
        "label": "Show Me Everything",
        "categories": [],
        "tags": [],
        "default_agencies": [],
        "default_frequency": "daily",
    },
}


INTEREST_OPTIONS: List[Dict[str, str]] = [
    {"key": key, "label": cfg["label"]} for key, cfg in INTEREST_CONFIG.items()
]


def get_interest_profile(key: str) -> Dict[str, object]:
    """
    Return the normalized config for a given interest key.
    Always falls back to the DEFAULT_INTEREST_KEY profile.
    """
    normalized = (key or "").strip().lower()
    cfg = INTEREST_CONFIG.get(normalized) or INTEREST_CONFIG[DEFAULT_INTEREST_KEY]
    return {
        "key": normalized or DEFAULT_INTEREST_KEY,
        "label": cfg["label"],
        "categories": list(cfg.get("categories", [])),
        "default_agencies": list(cfg.get("default_agencies", [])),
        "tags": list(cfg.get("tags", [])),
        "default_frequency": cfg.get("default_frequency", "daily"),
    }


def list_interest_options() -> List[Dict[str, str]]:
    """Return options in display order for forms."""
    order = [
        "construction",
        "professional_services",
        "it_technology",
        "facility_ops",
        "supplies_equipment",
        DEFAULT_INTEREST_KEY,
    ]
    seen = set()
    ordered: List[Dict[str, str]] = []
    for key in order:
        if key in INTEREST_CONFIG and key not in seen:
            ordered.append({"key": key, "label": INTEREST_CONFIG[key]["label"]})
            seen.add(key)
    # Include any future keys that didn't make the preferred order
    for key, cfg in INTEREST_CONFIG.items():
        if key not in seen:
            ordered.append({"key": key, "label": cfg["label"]})
    return ordered


def interest_label(key: str) -> str:
    """Human-readable label for a stored interest key."""
    resolved = get_interest_profile(key)
    return resolved["label"]
