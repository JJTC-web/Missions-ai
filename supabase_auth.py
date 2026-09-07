"""
Supabase Auth integration used to log into the /dashboard admin area.

Docs:
  https://supabase.com/docs/guides/auth/server-side/email-based-auth-with-pkce-flow
  https://supabase.com/docs/reference/api/introduction (PostgREST, for the admins table)

Auth:
  - Sign-in calls use the "apikey" header set to SUPABASE_ANON_KEY.
  - The admins-table lookup uses SUPABASE_SERVICE_ROLE_KEY, which bypasses
    row-level security, since this is a trusted server-side check.

Set environment variables:
   SUPABASE_URL
   SUPABASE_ANON_KEY
   SUPABASE_SERVICE_ROLE_KEY
"""

import os

import requests


def _supabase_url():
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url.rstrip("/")


def sign_in_with_password(email, password):
    """
    Authenticates against Supabase Auth. Returns the user's email on success.
    Raises RuntimeError with a user-facing message on failure.
    """
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not anon_key:
        raise RuntimeError("SUPABASE_ANON_KEY is not set")

    resp = requests.post(
        f"{_supabase_url()}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=15,
    )
    if not resp.ok:
        try:
            detail = resp.json().get("error_description") or resp.json().get("msg") or resp.text
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Supabase sign-in failed: {detail}")
    return resp.json()["user"]["email"]


def is_admin(email):
    """
    Checks the `admins` table (via the service role key, bypassing RLS) for
    the given email.
    """
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")

    resp = requests.get(
        f"{_supabase_url()}/rest/v1/admins",
        params={"email": f"eq.{email}", "select": "email"},
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return len(resp.json()) > 0


def admin_generate_invite_link(email, redirect_to):
    """
    Generates a Supabase Auth link for the Client Portal invite flow, using
    the Admin API (service role key) rather than Supabase's own invite
    email -- we send the email ourselves via Resend so it matches the rest
    of MissionOS AI's branding.

    A brand-new email gets an "invite" link (creates the Supabase Auth user
    and lets them set a password). An email that already has a Supabase
    Auth account -- e.g. re-inviting, or the contact already logged in
    once -- can't get a fresh "invite" link, so this falls back to a
    "recovery" (password reset) link for the same effect.

    Returns (action_link, auth_user_id).
    """
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(
        f"{_supabase_url()}/auth/v1/admin/generate_link",
        headers=headers,
        json={"type": "invite", "email": email, "options": {"redirect_to": redirect_to}},
        timeout=15,
    )
    if not resp.ok:
        resp = requests.post(
            f"{_supabase_url()}/auth/v1/admin/generate_link",
            headers=headers,
            json={"type": "recovery", "email": email, "options": {"redirect_to": redirect_to}},
            timeout=15,
        )
    if not resp.ok:
        try:
            detail = resp.json().get("msg") or resp.text
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Supabase invite link generation failed: {detail}")

    data = resp.json()
    return data["action_link"], data["user"]["id"]
