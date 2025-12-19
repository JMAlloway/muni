"""
Helpers for normalized company profile fields used by generators.
Profiles are stored as JSON blobs; we merge defaults without forcing schema migrations.
"""

from copy import deepcopy
from typing import Any, Dict, MutableMapping

# Hard limits to prevent accidental or maliciously large payloads.
_MAX_DEPTH = 10
_MAX_TOTAL_FIELDS = 256
_MAX_LIST_LENGTH = 100
_MAX_STRING_LENGTH = 100_000


# Keep defaults as a module-level constant so we can cheaply clone it.
_DEFAULT_COMPANY_PROFILE: Dict[str, Any] = {
    "legal_name": "",
    "dba": "",
    "entity_type": "",
    "state_of_incorporation": "",
    "year_established": "",
    "employee_count_ft": "",
    "employee_count_pt": "",
    "cage_code": "",
    "revenue_current": "",
    "revenue_prior": "",
    "revenue_two_years": "",
    "gsa_schedule": "",
    "years_experience": "",
    "hq_address": "",
    "business_address": {"street": "", "city": "", "state": "", "zip": ""},
    "phone": "",
    "email": "",
    "website": "",
    "service_area": "",
    "service_area_list": [],
    "service_categories": [],
    "company_overview": "",
    "experience": "",
    "offerings": "",
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
        "certifications": [],
        "certification_files": [],
    },
    "contractor_licenses": [
        {
            "state": "",
            "type": "",
            "number": "",
            "issuing_authority": "",
            "expiry": "",
        }
    ],
    "insurance": {
        "workers_comp_certificate": {"id": "", "expiry": ""},
        "general_liability": {
            "carrier": "",
            "policy_number": "",
            "per_occurrence_limit": "",
            "aggregate_limit": "",
            "effective": "",
            "expiry": "",
        },
        "auto_liability": {
            "carrier": "",
            "policy_number": "",
            "limit": "",
            "effective": "",
            "expiry": "",
        },
        "umbrella_excess": {
            "carrier": "",
            "policy_number": "",
            "limit": "",
            "effective": "",
            "expiry": "",
        },
        "emr_rate": "",
        "safety_program_details": "",
        "can_add_additional_insured": True,
    },
    "bonding": {
        "single_project_limit": "",
        "aggregate_limit": "",
        "surety_company": "",
        "surety_contact": "",
    },
    "bank_reference": {
        "bank_name": "",
        "contact_name": "",
        "phone": "",
        "account_tenure_years": "",
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
    "quality_certifications": [
        {"type": "", "number": "", "expiry": ""}
    ],
    "recent_projects": [
        {
            "project_name": "",
            "client_name": "",
            "owner_contact": "",
            "architect_engineer": "",
            "address": "",
            "phone": "",
            "location": "",
            "contract_value": "",
            "completion_date": "",
            "description": "",
            "dates": "",
        }
    ],
    "low_income_programs_supported": [
        {"program": "", "agency": "", "dates": "", "scope": ""}
    ],
    "avg_work_order_turnaround_days": "",
    "years_in_business": "",
    "avg_annual_revenue": "",
    "full_time_employees": "",
    "safety_program_description": "",
    "emr": "",
    "osha_incidents": "",
    "drug_free_workplace": False,
    "naics_codes": [],
    "sic_codes": [],
    "can_meet_timeframe": "",
    "residential_energy_program_experience": "",
    "compliance": {
        "non_collusion_certified": False,
        "prevailing_wage_compliant": False,
        "addenda_acknowledged": [],
        "contract_terms_agreed": False,
    },
    "subcontractors": [
        {
            "company_name": "",
            "trade": "",
            "address": "",
            "contact_name": "",
            "phone": "",
            "email": "",
            "license_number": "",
        }
    ],
    "attachments": {
        "cover_letter_template": "",
        "soq_sections": "",
        "insurance_cert_files": [],
        "workers_comp_file": "",
        "license_files": [],
        "training_plan_file": "",
    },
}


def default_company_profile() -> Dict[str, Any]:
    """
    Return a fresh, safe copy of the default company profile template.
    """
    return deepcopy(_DEFAULT_COMPANY_PROFILE)


def _sanitize_profile(
    profile: Dict[str, Any],
    template: Dict[str, Any],
    depth: int = 1,
    field_counter: MutableMapping[str, int] | None = None,
    allow_unknown: bool = True,
) -> Dict[str, Any]:
    """
    Validate and clone a user-provided profile, allowing only known keys and safe types.
    None values are treated as "missing" and will be replaced by defaults.
    """
    if not isinstance(profile, dict):
        raise ValueError("Company profile must be a dictionary.")

    if field_counter is None:
        field_counter = {"count": 0}

    if depth > _MAX_DEPTH:
        raise ValueError(f"Company profile exceeds maximum depth of {_MAX_DEPTH}.")

    sanitized: Dict[str, Any] = {}
    field_counter["count"] += len(profile)
    if field_counter["count"] > _MAX_TOTAL_FIELDS:
        raise ValueError(f"Company profile exceeds maximum field count of {_MAX_TOTAL_FIELDS}.")

    for key, value in profile.items():
        if key not in template:
            if not allow_unknown:
                raise ValueError(f"Unknown company profile field: {key}")
            if value is None:
                continue
            sanitized[key] = _sanitize_extra(value, depth=depth + 1, field_counter=field_counter)
            continue
        if value is None:
            continue

        sanitized[key] = _sanitize_value(
            value,
            template_value=template[key],
            depth=depth + 1,
            field_counter=field_counter,
        )

    return sanitized


def _sanitize_extra(value: Any, depth: int, field_counter: MutableMapping[str, int]) -> Any:
    """
    Sanitize values without a template (legacy/extra fields). Allows safe scalars and simple
    containers while still enforcing depth and size limits.
    """
    if depth > _MAX_DEPTH:
        raise ValueError(f"Company profile exceeds maximum depth of {_MAX_DEPTH}.")

    if isinstance(value, dict):
        field_counter["count"] += len(value)
        if field_counter["count"] > _MAX_TOTAL_FIELDS:
            raise ValueError(f"Company profile exceeds maximum field count of {_MAX_TOTAL_FIELDS}.")
        cleaned: Dict[str, Any] = {}
        for k, v in value.items():
            if v is None:
                continue
            cleaned[k] = _sanitize_extra(v, depth + 1, field_counter)
        return cleaned

    if isinstance(value, list):
        if len(value) > _MAX_LIST_LENGTH:
            raise ValueError(f"Company profile lists are limited to {_MAX_LIST_LENGTH} items.")
        field_counter["count"] += len(value)
        if field_counter["count"] > _MAX_TOTAL_FIELDS:
            raise ValueError(f"Company profile exceeds maximum field count of {_MAX_TOTAL_FIELDS}.")
        return [_sanitize_extra(v, depth + 1, field_counter) for v in value if v is not None]

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise ValueError(f"String values are limited to {_MAX_STRING_LENGTH} characters.")
        return value

    raise ValueError("Unsupported company profile value type.")


def _sanitize_value(value: Any, template_value: Any, depth: int, field_counter: MutableMapping[str, int]) -> Any:
    """
    Recursively validate a value against the template shape, enforcing depth/size limits.
    """
    if depth > _MAX_DEPTH:
        raise ValueError(f"Company profile exceeds maximum depth of {_MAX_DEPTH}.")

    if isinstance(template_value, dict):
        if not isinstance(value, dict):
            raise ValueError("Expected an object for company profile section.")
        return _sanitize_profile(value, template_value, depth=depth, field_counter=field_counter)

    if isinstance(template_value, list):
        if not isinstance(value, list):
            raise ValueError("Expected a list in company profile section.")
        if len(value) > _MAX_LIST_LENGTH:
            raise ValueError(f"Company profile lists are limited to {_MAX_LIST_LENGTH} items.")

        field_counter["count"] += len(value)
        if field_counter["count"] > _MAX_TOTAL_FIELDS:
            raise ValueError(f"Company profile exceeds maximum field count of {_MAX_TOTAL_FIELDS}.")

        element_template = template_value[0] if template_value else ""
        cleaned_list = []
        for element in value:
            if element is None:
                continue
            cleaned_list.append(
                _sanitize_value(element, template_value=element_template, depth=depth + 1, field_counter=field_counter)
            )
        return cleaned_list

    if isinstance(template_value, bool):
        if not isinstance(value, bool):
            raise ValueError("Expected a boolean value in company profile.")
        return value

    if isinstance(template_value, (int, float)) and not isinstance(template_value, bool):
        if not isinstance(value, (int, float)):
            raise ValueError("Expected a numeric value in company profile.")
        return value

    if isinstance(template_value, str):
        if not isinstance(value, str):
            raise ValueError("Expected a string value in company profile.")
        if len(value) > _MAX_STRING_LENGTH:
            raise ValueError(f"String values are limited to {_MAX_STRING_LENGTH} characters.")
        return value

    raise ValueError("Unsupported company profile value type.")


def _merge_defaults(target: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge sanitized overrides into target defaults without recursion beyond _MAX_DEPTH.
    Existing values in overrides always win.
    """
    stack = [(target, overrides, 1)]
    while stack:
        current_target, current_override, depth = stack.pop()
        if depth > _MAX_DEPTH:
            raise ValueError(f"Company profile exceeds maximum depth of {_MAX_DEPTH}.")

        for key, override_value in current_override.items():
            base_value = current_target.get(key)
            if isinstance(base_value, dict) and isinstance(override_value, dict):
                stack.append((base_value, override_value, depth + 1))
            else:
                current_target[key] = override_value

    return target


def merge_company_profile_defaults(profile: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Return profile merged with defaults; existing values win, and inputs are validated.
    """
    base = default_company_profile()
    if profile is None:
        return base

    sanitized = _sanitize_profile(profile, _DEFAULT_COMPANY_PROFILE)
    if not sanitized:
        return base

    return _merge_defaults(base, sanitized)
