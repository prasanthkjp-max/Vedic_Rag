"""Digest domain: daily email/WhatsApp digest opt-in and the WhatsApp Business
Cloud API webhook (delivery status + STOP opt-out)."""
import json
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from src.core.config import DB_PATH, PORTAL_BASE_URL, WHATSAPP_VERIFY_TOKEN, connect_db
from src.services.whatsapp_sender import verify_whatsapp_signature
from src.api.deps import logger, LangCode, get_user_by_session, _session_user_or_401

router = APIRouter()


# --- app.py:5466-5580 ---
# --- Daily digest subscription (free retention feature; the actual sending is
# done by the cron-invoked tools/send_digests.py, never by this process) ---

# The channels a digest can be delivered on. 'email' is always available;
# 'whatsapp' requires a validated number + explicit opt-in (checked at subscribe).
DIGEST_CHANNELS = ("email", "whatsapp")


class DigestSubscribeRequest(BaseModel):
    language: Optional[LangCode] = None
    channels: Optional[list[str]] = None


@router.get("/api/user/digest")
def digest_status(request: Request):
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        row = conn.execute(
            "SELECT enabled, language, last_sent_date, channels FROM digest_subscriptions WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"subscribed": False}
    channels = (row[3] or "email").split(",")
    return {"subscribed": bool(row[0]), "language": row[1], "last_sent_date": row[2], "channels": channels}


@router.post("/api/user/digest/subscribe")
def digest_subscribe(req: DigestSubscribeRequest, request: Request):
    user = _session_user_or_401(request)
    # The digest is personalised to the natal chart — without saved birth
    # details there is nothing to compute, so fail with a clear instruction.
    if not (user.get("dob") and user.get("tob")):
        raise HTTPException(
            status_code=400,
            detail="Save your birth details in your profile first — the daily digest is personalised to your chart.",
        )
    lang = req.language or user.get("language") or "en"
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT id, channels FROM digest_subscriptions WHERE user_id = ?", (user["id"],)
        ).fetchone()
        # Resolve delivery channels: when the client omits `channels`, PRESERVE
        # the existing selection (a plain re-subscribe must not silently drop a
        # WhatsApp channel the user already enabled) rather than resetting to
        # email-only. Validate the enum; never enable whatsapp without consent.
        existing = (row[1].split(",") if (row and row[1]) else ["email"])
        requested = req.channels if req.channels is not None else existing
        channels = [c for c in requested if c in DIGEST_CHANNELS] or ["email"]
        if "whatsapp" in channels and not (user.get("whatsapp_opt_in") and user.get("phone_number")):
            raise HTTPException(
                status_code=400,
                detail="Enable WhatsApp delivery (add a number and opt in) before choosing the WhatsApp channel.",
            )
        channels_str = ",".join(channels)
        if row:
            cursor.execute(
                "UPDATE digest_subscriptions SET enabled = 1, language = ?, channels = ? WHERE user_id = ?",
                (lang, channels_str, user["id"]),
            )
        else:
            cursor.execute(
                "INSERT INTO digest_subscriptions (user_id, enabled, language, unsubscribe_token, channels) VALUES (?, 1, ?, ?, ?)",
                (user["id"], lang, secrets.token_urlsafe(16), channels_str),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "subscribed": True, "language": lang}


@router.post("/api/user/digest/unsubscribe")
def digest_unsubscribe(request: Request):
    user = _session_user_or_401(request)
    conn = connect_db(DB_PATH)
    try:
        conn.execute(
            "UPDATE digest_subscriptions SET enabled = 0 WHERE user_id = ?", (user["id"],)
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "subscribed": False}


@router.get("/digest/unsubscribe/{token}")
def digest_unsubscribe_link(token: str):
    """Public one-click opt-out target for the link in every digest email.
    The token is the credential; no session is required."""
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE digest_subscriptions SET enabled = 0 WHERE unsubscribe_token = ?",
            (token,),
        )
        found = cursor.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    if not found:
        raise HTTPException(status_code=404, detail="Unknown unsubscribe link")
    return HTMLResponse(
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Unsubscribed</title></head>"
        "<body style='font-family:sans-serif;background:#12101c;color:#eee;display:flex;"
        "align-items:center;justify-content:center;height:100vh'>"
        "<div style='text-align:center'><h2>🙏 You have been unsubscribed.</h2>"
        f"<p>You will no longer receive the daily digest.</p>"
        f"<p><a style='color:#d4af37' href='{PORTAL_BASE_URL}/'>Back to the portal</a></p></div></body></html>"
    )


# --- app.py:5610-5700 ---
# --- WhatsApp Business Cloud API webhook (delivery status + STOP opt-out) ---
# Joins the open-paths list (no session/API key) but validates the Meta
# X-Hub-Signature-256 HMAC strictly before trusting any payload. The GET is the
# one-time Meta subscription handshake (echoes hub.challenge when the verify
# token matches).

# STOP keywords across the six supported languages (case/space-insensitive).
_WHATSAPP_STOP_WORDS = {
    "stop", "unsubscribe", "cancel",
    "நிறுத்து", "நிறுத்தவும்",            # Tamil
    "ఆపు", "ఆపండి",                       # Telugu
    "നിർത്തുക", "നിര്‍ത്തുക",              # Malayalam
    "ನಿಲ್ಲಿಸಿ", "ನಿಲ್ಲಿಸು",                # Kannada
    "बंद", "बंदकरो", "रोको",              # Hindi
}


def _optout_whatsapp_by_phone(phone_e164: str) -> bool:
    """Immediately revoke WhatsApp consent for the account holding this number.
    Returns True if a row was updated. The number arrives from Meta without a
    leading '+', so we match against the stored E.164 by digits."""
    digits = "".join(c for c in (phone_e164 or "") if c.isdigit())
    if not digits:
        return False
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        # Stored numbers are +<digits>; Meta sends bare <digits>. Compare the
        # digit tails so both forms match.
        cursor.execute(
            "UPDATE users SET whatsapp_opt_in = 0, whatsapp_opt_in_at = NULL "
            "WHERE REPLACE(phone_number, '+', '') = ?",
            (digits,),
        )
        changed = cursor.rowcount > 0
        conn.commit()
    finally:
        conn.close()
    return changed


@router.get("/api/whatsapp/webhook")
def whatsapp_webhook_verify(request: Request):
    """Meta webhook subscription handshake: echo hub.challenge iff the verify
    token matches WHATSAPP_VERIFY_TOKEN. Fails closed when unconfigured."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token") or ""
    challenge = params.get("hub.challenge", "")
    # Constant-time compare of the verify token (a secret), consistent with the
    # signature checks elsewhere; fails closed when the token is unconfigured.
    if mode == "subscribe" and WHATSAPP_VERIFY_TOKEN and secrets.compare_digest(token, WHATSAPP_VERIFY_TOKEN):
        # Meta expects the raw challenge echoed back as text/plain.
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed.")


@router.post("/api/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """Receive delivery statuses and inbound messages from Meta.

    Strictly verifies X-Hub-Signature-256 (HMAC-SHA256 of the raw body keyed by
    WHATSAPP_WEBHOOK_SECRET) before trusting anything. An inbound "STOP"/
    "UNSUBSCRIBE" (in any supported language) auto-revokes that number's opt-in.
    """
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    if not verify_whatsapp_signature(raw, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")

    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed webhook body.")

    # Walk the standard Cloud API envelope: entry[].changes[].value.messages[].
    for entry in event.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                body = (msg.get("text", {}).get("body") or "").strip().lower()
                # Normalise: drop whitespace so "stop", "STOP", " stop " all match.
                if body.replace(" ", "") in {w.lower().replace(" ", "") for w in _WHATSAPP_STOP_WORDS}:
                    from_phone = msg.get("from", "")
                    if _optout_whatsapp_by_phone(from_phone):
                        logger.info("WhatsApp STOP honored for %s", from_phone[:6] + "…")

    # Always 200 a verified event so Meta stops retrying.
    return {"status": "ok"}


