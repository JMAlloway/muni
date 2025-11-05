import os, mimetypes, uuid
from typing import Optional, Tuple

USE_S3 = bool(os.getenv("DOCS_BUCKET"))
BUCKET  = os.getenv("DOCS_BUCKET", "")
LOCAL_DIR = os.getenv("LOCAL_UPLOAD_DIR", "uploads")

if USE_S3:
    import boto3
    _s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )

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
