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
    ):
        return list_url

    # Some portals (COTA / CRAA gob2g) use ProposalSearchPublicDetail.asp with RID=...
    # Treat those as valid detail pages when an RID is present; otherwise fall back to list.
    if "proposalsearchpublicdetail.asp" in u:
        return source_url if "rid=" in u else list_url

    return source_url
