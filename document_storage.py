"""
Supabase Storage integration for the Client Portal's Document Vault.

Files live in a private Supabase Storage bucket (ORG_DOCUMENTS_BUCKET) and
are always served through our own /dashboard and /portal routes -- which
check admin/client-portal auth first -- rather than via Supabase signed
URLs, so the service role key never leaves the server.

Docs: https://supabase.com/docs/guides/storage
Auth: header "Authorization: Bearer {SUPABASE_SERVICE_ROLE_KEY}"

Environment variables:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

import os

import requests

ORG_DOCUMENTS_BUCKET = "org-documents"


def _supabase_url():
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url.rstrip("/")


def _headers():
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return {"apikey": service_key, "Authorization": f"Bearer {service_key}"}


def ensure_bucket():
    """Idempotently creates the private org-documents bucket if it doesn't
    exist yet, so there's no manual Supabase dashboard step to forget."""
    resp = requests.post(
        f"{_supabase_url()}/storage/v1/bucket",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"id": ORG_DOCUMENTS_BUCKET, "name": ORG_DOCUMENTS_BUCKET, "public": False},
        timeout=15,
    )
    if resp.ok or "already exists" in resp.text.lower() or "Duplicate" in resp.text:
        return
    resp.raise_for_status()


def upload_document(storage_path, file_bytes, content_type):
    """Uploads (or overwrites) a file at storage_path within the private bucket."""
    ensure_bucket()
    resp = requests.post(
        f"{_supabase_url()}/storage/v1/object/{ORG_DOCUMENTS_BUCKET}/{storage_path}",
        headers={
            **_headers(),
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
        data=file_bytes,
        timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"Supabase Storage upload failed ({resp.status_code}): {resp.text}")


def download_document(storage_path):
    """Returns (file_bytes, content_type) for a stored document."""
    resp = requests.get(
        f"{_supabase_url()}/storage/v1/object/{ORG_DOCUMENTS_BUCKET}/{storage_path}",
        headers=_headers(),
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Supabase Storage download failed ({resp.status_code}): {resp.text}")
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
