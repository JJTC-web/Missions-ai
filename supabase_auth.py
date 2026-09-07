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


def _admin_headers():
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def _generate_link(link_type, email, redirect_to):
    resp = requests.post(
        f"{_supabase_url()}/auth/v1/admin/generate_link",
        headers=_admin_headers(),
        json={"type": link_type, "email": email, "options": {"redirect_to": redirect_to}},
        timeout=15,
    )
    return resp


def _extract_link_result(data):
    """The raw GoTrue REST response merges the user's fields (id, email,
    ...) directly at the top level alongside the link properties
    (action_link, ...) -- there's no nested "user" object, unlike what
    some client SDKs construct from it. Fall back to a nested "user" key
    too, in case that ever differs by Supabase version."""
    auth_user_id = data.get("id") or data.get("user", {}).get("id")
    if not auth_user_id:
        raise RuntimeError(f"Supabase response didn't include a user id: {data}")
    return data["action_link"], auth_user_id


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
    resp = _generate_link("invite", email, redirect_to)
    if not resp.ok:
        resp = _generate_link("recovery", email, redirect_to)
    if not resp.ok:
        try:
            detail = resp.json().get("msg") or resp.text
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Supabase invite link generation failed: {detail}")

    return _extract_link_result(resp.json())


def admin_generate_recovery_link(email, redirect_to):
    """
    Generates a Supabase Auth password-reset link for an existing user, for
    the portal's "Forgot your password?" flow. Unlike admin_generate_invite_link,
    this never falls back to "invite" -- an email with no Supabase Auth
    account should fail here rather than silently create one, so the
    caller can treat "no such account" the same as "email sent" (never
    reveal which emails have portal access).

    Returns (action_link, auth_user_id). Raises RuntimeError if the email
    has no Supabase Auth account or the request otherwise fails.
    """
    resp = _generate_link("recovery", email, redirect_to)
    if not resp.ok:
        try:
            detail = resp.json().get("msg") or resp.text
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"Supabase recovery link generation failed: {detail}")

    return _extract_link_result(resp.json())
