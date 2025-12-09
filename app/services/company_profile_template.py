"""
Helpers for normalized company profile fields used by generators.
Profiles are stored as JSON blobs; we merge defaults without forcing schema migrations.
"""

from copy import deepcopy
from typing import Any, Dict


def default_company_profile() -> Dict[str, Any]:
    return {
        "legal_name": "",
        "entity_type": "",
        "hq_address": "",
        "website": "",
        "primary_contact": {
            "name": "",
            "title": "",
            "phone": "",
            "email": "",
        },
        "authorized_signatory": {
            "name": "",
            "title": "",
            "phone": "",
            "email": "",
        },
        "sole_responsibility_statement": "",
        "certifications_status": {
            "MBE": False,
            "SBE": False,
            "EDGE": False,
            "WBE": False,
            "details": "",
        },
        "contractor_licenses": [
            {
                "state": "",
                "number": "",
                "expiry": "",
            }
        ],
        "insurance": {
            "workers_comp_certificate": {"id": "", "expiry": ""},
            "liability_insurance": {"carrier": "", "policy_number": "", "limits": "", "expiry": ""},
            "can_add_additional_insured": True,
        },
        "criminal_history_check_policy": "",
        "recordkeeping_controls": "",
        "key_personnel": [
            {"name": "", "role": "", "phone": "", "email": "", "bio": ""}
        ],
        "training_and_certifications": [
            {
                "person": "",
                "trainings_completed": [],
                "trainings_planned": [],
                "certifications": [],
            }
        ],
        "recent_projects": [
            {
                "client_name": "",
                "address": "",
                "phone": "",
                "description": "",
                "dates": "",
            }
        ],
        "low_income_programs_supported": [
            {"program": "", "agency": "", "dates": "", "scope": ""}
        ],
        "avg_work_order_turnaround_days": "",
        "can_meet_timeframe": "",
        "residential_energy_program_experience": "",
        "service_area": "",
        "attachments": {
            "cover_letter_template": "",
            "soq_sections": "",
            "insurance_cert_files": [],
            "workers_comp_file": "",
            "license_files": [],
            "training_plan_file": "",
        },
    }


def merge_company_profile_defaults(profile: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Return profile merged with defaults; existing values win.
    """
    base = default_company_profile()
    if not profile:
        return base

    def _merge(a, b):
        # merge b into a
        for k, v in b.items():
            if k in a and isinstance(a[k], dict) and isinstance(v, dict):
                _merge(a[k], v)
            elif k in a and isinstance(a[k], list) and isinstance(v, list):
                # keep existing list; if empty, apply default structure
                if not a[k]:
                    a[k] = deepcopy(v)
            else:
                if k not in a:
                    a[k] = v
        return a

    return _merge(deepcopy(profile), base)
