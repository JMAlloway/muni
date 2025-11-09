"""Compatibility shim for legacy router imports."""

from importlib import import_module

_router_modules = [
    "admin",
    "auth_web",
    "bid_tracker",
    "columbus_airports_detail",
    "columbus_detail",
    "cota_detail",
    "debug_cookies",
    "dev_auth",
    "gahanna_detail",
    "marketing",
    "onboarding",
    "opportunities",
    "opportunity_web",
    "preferences",
    "tracker_dashboard",
    "uploads",
    "users",
    "vendor_guides",
    "zip",
]

for name in _router_modules:
    module = import_module(f"app.api.{name}")
    globals()[name] = module

__all__ = _router_modules
