# app/ingest/utils.py
def safe_source_url(agency_name: str, source_url: str, list_url: str) -> str:
    """
    Ensures source_url is always publicly accessible.
    If it looks broken (javascript:, RID=UNKNOWN, etc.), returns list_url instead.
    """
    if not source_url:
        return list_url

    u = source_url.strip().lower()
    if (
        u.startswith("javascript:")
        or u == "#"
        or u == "about:blank"
        or "rid=unknown" in u
        or "proposalsearchpublicdetail.asp" in u  # COTA / Bonfire / etc.
    ):
        return list_url

    return source_url
