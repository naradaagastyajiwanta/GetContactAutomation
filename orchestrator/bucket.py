"""
Object storage for ig_posts image cache.
Supports Google Cloud Storage (GCS) and S3-compatible providers (R2, AWS S3).

Config vars (.env.production):

  GCS (recommended — set GCS_SERVICE_ACCOUNT_JSON):
    BUCKET_PROVIDER          = gcs
    GCS_SERVICE_ACCOUNT_JSON = <contents of service account JSON>
    BUCKET_NAME              = your-bucket-name
    BUCKET_PUBLIC_URL        = https://storage.googleapis.com/your-bucket-name
                               or custom domain if configured

  S3-compatible (Cloudflare R2, AWS S3, etc.):
    BUCKET_PROVIDER     = s3   (or leave empty — s3 is default)
    BUCKET_ENDPOINT_URL = https://<account>.r2.cloudflarestorage.com
    BUCKET_ACCESS_KEY   = <key id>
    BUCKET_SECRET_KEY   = <secret>
    BUCKET_NAME         = your-bucket-name
    BUCKET_PUBLIC_URL   = https://images.yourdomain.com
    BUCKET_REGION       = auto
"""
from __future__ import annotations

import asyncio
import hashlib
import json

from orchestrator.config import cfg, log


def _provider() -> str:
    return str(cfg.get("BUCKET_PROVIDER") or "s3").lower()


def _bucket_name() -> str:
    return str(cfg.get("BUCKET_NAME") or "")


def _public_url() -> str:
    return str(cfg.get("BUCKET_PUBLIC_URL") or "").rstrip("/")


def is_configured() -> bool:
    if not _bucket_name() or not _public_url():
        return False
    if _provider() == "gcs":
        return bool(cfg.get("GCS_SERVICE_ACCOUNT_JSON"))
    # S3
    return bool(cfg.get("BUCKET_ENDPOINT_URL") and cfg.get("BUCKET_ACCESS_KEY") and cfg.get("BUCKET_SECRET_KEY"))


def _folder_prefix() -> str:
    folder = str(cfg.get("BUCKET_FOLDER") or "").strip("/")
    return f"{folder}/" if folder else ""


def make_key(post_url: str, university_id: int) -> str:
    """Generate a stable, unique storage key from post URL."""
    url_hash = hashlib.sha256(post_url.encode()).hexdigest()[:16]
    return f"{_folder_prefix()}ig_posts/{university_id}/{url_hash}.jpg"


def _upload_gcs_sync(key: str, data: bytes, content_type: str) -> str | None:
    from google.cloud import storage as gcs
    from google.oauth2 import service_account

    try:
        sa_json = str(cfg.get("GCS_SERVICE_ACCOUNT_JSON") or "")
        sa_info = json.loads(sa_json)
        credentials = service_account.Credentials.from_service_account_info(sa_info)
        client = gcs.Client(project=sa_info.get("project_id"), credentials=credentials)
        bucket = client.bucket(_bucket_name())
        blob = bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return f"{_public_url()}/{key}"
    except Exception as exc:
        log.warning("[Bucket/GCS] Upload failed for %s: %s", key, exc)
        return None


def _upload_s3_sync(key: str, data: bytes, content_type: str) -> str | None:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=str(cfg.get("BUCKET_ENDPOINT_URL") or ""),
            aws_access_key_id=str(cfg.get("BUCKET_ACCESS_KEY") or ""),
            aws_secret_access_key=str(cfg.get("BUCKET_SECRET_KEY") or ""),
            region_name=str(cfg.get("BUCKET_REGION") or "auto"),
        )
        s3.put_object(Bucket=_bucket_name(), Key=key, Body=data, ContentType=content_type)
        return f"{_public_url()}/{key}"
    except (BotoCoreError, ClientError) as exc:
        log.warning("[Bucket/S3] Upload failed for %s: %s", key, exc)
        return None
    except Exception as exc:
        log.warning("[Bucket/S3] Unexpected error uploading %s: %s", key, exc)
        return None


async def upload_image(
    post_url: str,
    university_id: int,
    image_bytes: bytes,
    content_type: str = "image/jpeg",
) -> str | None:
    """Upload image bytes to bucket. Returns public URL or None on failure."""
    if not is_configured():
        return None
    key = make_key(post_url, university_id)
    fn = _upload_gcs_sync if _provider() == "gcs" else _upload_s3_sync
    url = await asyncio.to_thread(fn, key, image_bytes, content_type)
    if url:
        log.debug("[Bucket] Uploaded %s → %s", key, url)
    return url
