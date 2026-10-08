"""Logs the harness into Lenses with OAuth: authorization code plus PKCE, against the server built into HQ.

The harness acts for the person who logs in and asks for the read scope only.
With a read token the Lenses MCP server hides every tool that writes and HQ
refuses writes sent through SQL. Tokens live outside the source tree, so they
survive every reload and the harness refreshes them before they expire.

One HQ, two addresses: your browser reaches it at the issuer URL (localhost),
and the harness reaches it on the Compose network (LENSES_HQ_URL).
"""

import base64
import hashlib
import json
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx

from harness import settings

SCOPE = "read"  # least privilege: the harness never asks for write or delete
_lock = threading.Lock()


class LoginRequired(RuntimeError):
    def __init__(self, why: str):
        super().__init__(f"{why}. Log into Lenses at {settings.HARNESS_URL}/login")


def redirect_uri() -> str:
    return f"{settings.HARNESS_URL}/oauth/callback"


def start_login() -> str:
    """Register the harness with HQ (dynamic client registration) and return the URL for your browser."""
    metadata = _metadata()
    registration = {
        "client_name": "Let's Build an Agent Harness",
        "redirect_uris": [redirect_uri()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # a public client: PKCE instead of a client secret
        "scope": SCOPE,
    }
    response = httpx.post(_internal(metadata["registration_endpoint"], metadata), json=registration, timeout=10)
    response.raise_for_status()
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(16)
    with _lock:
        stored = _load()
        stored["pending"] = {"state": state, "verifier": verifier, "client_id": response.json()["client_id"]}
        _save(stored)
    query = {
        "response_type": "code",
        "client_id": stored["pending"]["client_id"],
        "redirect_uri": redirect_uri(),
        "scope": SCOPE,
        "state": state,
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
        "code_challenge_method": "S256",
        "resource": settings.LENSES_MCP_URL,
    }
    return f"{metadata['authorization_endpoint']}?{urlencode(query)}"


def finish_login(code: str, state: str) -> dict:
    """HQ sent your browser back with a code. Swap it for tokens and keep them."""
    with _lock:
        pending = _load().get("pending") or {}
        if not pending or not secrets.compare_digest(state, pending["state"]):
            raise LoginRequired("this login has expired or was already used")
        form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri()}
        tokens = _token_request({**form, "code_verifier": pending["verifier"], "client_id": pending["client_id"]})
        stored = {"client_id": pending["client_id"], **tokens}
        _save(stored)
        return stored


def access_token() -> str:
    """A valid access token, refreshed first if it expires within a minute."""
    with _lock:
        stored = _load()
        if not stored.get("access_token"):
            raise LoginRequired("the harness has not logged into Lenses yet")
        if stored["expires_at"] - time.time() > 60:
            return stored["access_token"]
        if not stored.get("refresh_token"):
            raise LoginRequired("the Lenses login has expired")
        form = {"grant_type": "refresh_token", "refresh_token": stored["refresh_token"]}
        stored.update({k: v for k, v in _token_request({**form, "client_id": stored["client_id"]}).items() if v})
        _save(stored)
        return stored["access_token"]


def status() -> str:
    access_token()
    stored = _load()
    return f"scope {stored['scope']}, token valid for {int(stored['expires_at'] - time.time()) // 60} more minutes"


def _token_request(form: dict) -> dict:
    metadata = _metadata()
    response = httpx.post(
        _internal(metadata["token_endpoint"], metadata), data={**form, "resource": settings.LENSES_MCP_URL}, timeout=10
    )
    if response.status_code != 200:
        raise LoginRequired(f"HQ refused the token request ({response.status_code}: {response.text[:200]})")
    token = response.json()
    return {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "scope": token.get("scope", SCOPE),
        "expires_at": time.time() + token.get("expires_in", 3600),
    }


def _metadata() -> dict:
    """RFC 8414 discovery, over the Compose network."""
    try:
        response = httpx.get(f"{settings.LENSES_HQ_URL}/.well-known/oauth-authorization-server", timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"cannot reach Lenses HQ at {settings.LENSES_HQ_URL}: {exc}") from exc
    return response.json()


def _internal(url: str, metadata: dict) -> str:
    """The same HQ endpoint, at the address the harness can reach."""
    return url.replace(metadata["issuer"].rstrip("/"), settings.LENSES_HQ_URL.rstrip("/"), 1)


def _load() -> dict:
    try:
        return json.loads(settings.OAUTH_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(stored: dict) -> None:
    settings.OAUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    partial = settings.OAUTH_STATE_FILE.with_suffix(".partial")
    partial.write_text(json.dumps(stored, indent=2))
    partial.chmod(0o600)
    partial.replace(settings.OAUTH_STATE_FILE)
