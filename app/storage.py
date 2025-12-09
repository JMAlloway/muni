import os, mimetypes, uuid
from typing import Optional, Tuple
from app.core.settings import settings

USE_S3 = bool(settings.DOCS_BUCKET)
BUCKET  = settings.DOCS_BUCKET or ""
LOCAL_DIR = settings.LOCAL_UPLOAD_DIR or "uploads"
_s3 = None  # populated when USE_S3 is True

def _build_s3_client():
    import boto3
    from botocore.config import Config
    endpoint = settings.S3_ENDPOINT_URL  # e.g. https://<accountid>.r2.cloudflarestorage.com
    aws_region = settings.AWS_REGION or "us-east-1"  # R2 accepts 'auto' or a region
    access_key = settings.AWS_ACCESS_KEY_ID
    secret_key = settings.AWS_SECRET_ACCESS_KEY
    addressing = settings.S3_ADDRESSING_STYLE or "virtual"  # or 'path' if needed

    return boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=aws_region,
        endpoint_url=endpoint,
        config=Config(signature_version="s3v4", s3={"addressing_style": addressing}),
    )

if USE_S3:
    _s3 = _build_s3_client()

def _safe_filename(name: str) -> str:
    keep = "".join(c for c in name if c.isalnum() or c in (" ", ".", "_", "-", "(", ")"))
    return keep.strip() or str(uuid.uuid4())

def store_bytes(user_id: int, opportunity_id: int, data: bytes, original_name: str, content_type: Optional[str]) -> Tuple[str, int, str]:
    """
    Returns: (storage_key, size, mime)
    storage_key is an S3 key OR local path.
    """
    fname = _safe_filename(original_name)
    mime  = content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
    size  = len(data)

    if USE_S3:
        key = f"prod/{user_id}/{opportunity_id}/{uuid.uuid4()}_{fname}"
        _s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=mime)
        return key, size, mime
    else:
        os.makedirs(os.path.join(LOCAL_DIR, str(user_id), str(opportunity_id)), exist_ok=True)
        key = os.path.join(LOCAL_DIR, str(user_id), str(opportunity_id), f"{uuid.uuid4()}_{fname}")
        with open(key, "wb") as f:
            f.write(data)
        return key, size, mime

def store_knowledge_bytes(user_id: str, team_id: Optional[str], data: bytes, original_name: str, content_type: Optional[str]) -> Tuple[str, int, str]:
    """
    Store reusable knowledge-base documents under a dedicated prefix (S3) or folder (local).
    Returns: (storage_key, size, mime)
    """
    fname = _safe_filename(original_name)
    mime = content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"
    size = len(data)
    owner = team_id or user_id

    if USE_S3:
        key = f"knowledge/{owner}/{uuid.uuid4()}_{fname}"
        _s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=mime)
        return key, size, mime

    base_dir = os.path.join(LOCAL_DIR, "knowledge", str(owner))
    os.makedirs(base_dir, exist_ok=True)
    key = os.path.join(base_dir, f"{uuid.uuid4()}_{fname}")
    with open(key, "wb") as f:
        f.write(data)
    return key, size, mime

def create_presigned_get(storage_key: str, expires: int = 900) -> str:
    if USE_S3:
        return _s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": BUCKET, "Key": storage_key},
            ExpiresIn=expires
        )
    else:
        # Local mode: serve via FastAPI streaming route
        return f"/uploads/local/{storage_key}"


def read_storage_bytes(storage_key: str) -> bytes:
    """
    Fetch raw bytes from storage_key (S3 or local). Best-effort; raises on failures.
    """
    if USE_S3:
        obj = _s3.get_object(Bucket=BUCKET, Key=storage_key)
        return obj["Body"].read()

    # Local disk fallback: ensure we don't leave uploads/ root
    base = os.path.abspath(LOCAL_DIR)
    abspath = os.path.abspath(storage_key)
    if not abspath.startswith(base):
        # Most knowledge keys will already be an absolute path under LOCAL_DIR
        abspath = os.path.abspath(os.path.join(base, storage_key))
    with open(abspath, "rb") as f:
        return f.read()


def store_profile_file(user_id: int, field: str, data: bytes, original_name: str, content_type: Optional[str]) -> str:
    """
    Store a company profile file to Cloudflare R2 (or local uploads) and return the key/path.
    Files are nested under company_profiles/{user_id}/ to keep them isolated.
    """
    fname = _safe_filename(original_name or field)
    mime = content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"

    if USE_S3:
        key = f"company_profiles/{user_id}/{fname}"
        _s3.put_object(Bucket=BUCKET, Key=key, Body=data, ContentType=mime)
        return key

    # Local disk fallback
    base_dir = os.path.join(LOCAL_DIR, "company_profiles", str(user_id))
    os.makedirs(base_dir, exist_ok=True)
    key = os.path.join(base_dir, fname)
    with open(key, "wb") as f:
        f.write(data)
    return key
