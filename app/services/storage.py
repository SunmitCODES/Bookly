"""Cloudflare R2 storage (S3-compatible via boto3).

Used for business logo uploads. The bucket is public-read; we store the
resulting public URL in Business.logo_url so Cloudflare serves the image
directly (no app bandwidth).
"""
import secrets

import boto3

from app.config import settings

ALLOWED_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MAX_BYTES = 2 * 1024 * 1024  # 2 MB


class StorageError(Exception):
    """Raised for validation / configuration problems (caller maps to HTTP)."""


def is_configured() -> bool:
    return all(
        [
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
            settings.r2_bucket,
            settings.r2_public_base_url,
        ]
    )


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def validate_image(content_type: str, size: int) -> str:
    """Return the file extension for a valid image, else raise StorageError."""
    if content_type not in ALLOWED_TYPES:
        raise StorageError("Logo must be a PNG, JPEG, or WebP image.")
    if size > MAX_BYTES:
        raise StorageError("Logo must be 2 MB or smaller.")
    return ALLOWED_TYPES[content_type]


def upload_logo(business_id, file_bytes: bytes, content_type: str) -> str:
    """Validate + upload a logo to R2; return its public URL."""
    if not is_configured():
        raise StorageError("Image storage is not configured.")
    ext = validate_image(content_type, len(file_bytes))
    key = f"logos/{business_id}/{secrets.token_urlsafe(8)}.{ext}"
    _s3_client().put_object(
        Bucket=settings.r2_bucket,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    return f"{settings.r2_public_base_url.rstrip('/')}/{key}"
