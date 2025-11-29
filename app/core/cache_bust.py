"""
Cache busting utility for static assets.
Automatically appends modification timestamps to asset URLs to ensure browsers load fresh versions.
"""
import os
from functools import lru_cache
from typing import Optional


@lru_cache(maxsize=128)
def get_asset_version(asset_path: str) -> str:
    """
    Get cache-busting version string for a static asset based on file modification time.

    Args:
        asset_path: Path relative to static root (e.g., "css/base.css")

    Returns:
        Version string (modification timestamp) or empty string if file not found
    """
    # Construct full path from project root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    full_path = os.path.join(base_dir, "app", "web", "static", asset_path)

    try:
        # Get file modification time as version
        mtime = os.path.getmtime(full_path)
        return str(int(mtime))
    except (OSError, FileNotFoundError):
        # File doesn't exist, return empty version
        return ""


def versioned_static(asset_path: str) -> str:
    """
    Generate a versioned static asset URL with automatic cache busting.

    Args:
        asset_path: Path relative to /static/ (e.g., "css/base.css")

    Returns:
        Full URL with version parameter (e.g., "/static/css/base.css?v=1234567890")

    Example:
        versioned_static("css/base.css") -> "/static/css/base.css?v=1234567890"
    """
    version = get_asset_version(asset_path)
    url = f"/static/{asset_path}"

    if version:
        return f"{url}?v={version}"
    return url


def clear_cache():
    """Clear the asset version cache. Useful for development/testing."""
    get_asset_version.cache_clear()
