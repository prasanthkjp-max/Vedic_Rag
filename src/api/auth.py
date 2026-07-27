"""Auth domain: signup/login, phone OTP, Google/Facebook OAuth, sessions,
and the profile-update endpoint.
"""
import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.config import (
    DB_PATH,
    MSG91_AUTH_KEY,
    MSG91_OTP_TEMPLATE_ID,
    ALLOW_MOCK_OAUTH,
    SIGNUP_BONUS_CREDITS,
    GOOGLE_OAUTH_CLIENT_ID,
    FACEBOOK_APP_ID,
    FACEBOOK_APP_SECRET,
    connect_db,
)
from src.api.deps import (
    logger,
    LangCode,
    get_user_by_session,
    hash_password,
    verify_password,
    _new_referral_code,
    _apply_referral,
)

router = APIRouter()


# --- app.py:972-996 ---
class SignupRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=512)
    full_name: str = Field(max_length=200)
    referral_code: str = Field(default="", max_length=32)

class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=512)

class SendOTPRequest(BaseModel):
    phone_number: str = Field(max_length=20)
    channel: str = Field(default="sms", max_length=10) # SMS only (MSG91)

class VerifyOTPRequest(BaseModel):
    phone_number: str = Field(max_length=20)
    otp: str = Field(max_length=10)
    referral_code: str = Field(default="", max_length=32)

class OAuthRequest(BaseModel):
    provider: str = Field(max_length=32)
    email: str = Field(max_length=320)
    name: str = Field(max_length=200)
    token: str = Field(max_length=8192)
    referral_code: str = Field(default="", max_length=32)


# --- app.py:2890-2924 ---
# E.164: a leading '+', a non-zero country-code digit, then up to 14 more
# digits (15 total max). WhatsApp delivery requires this exact shape.
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def _normalize_e164(raw: str) -> str:
    """Coerce a user-entered phone to E.164 or raise 400.

    Accepts common separators/spaces and a leading 00 international prefix,
    strips them, then validates the canonical +<digits> form. Never trust the
    client to have pre-formatted it.
    """
    s = re.sub(r"[\s().-]", "", (raw or "").strip())
    if s.startswith("00"):
        s = "+" + s[2:]
    if not _E164_RE.match(s):
        raise HTTPException(
            status_code=400,
            detail="Enter your phone in international E.164 format, e.g. +919876543210.",
        )
    return s


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(default=None, max_length=200)
    latitude: float = Field(default=None, ge=-90.0, le=90.0)
    longitude: float = Field(default=None, ge=-180.0, le=180.0)
    timezone: str = Field(default=None, max_length=64)
    language: LangCode = None
    location_name: str = Field(default=None, max_length=200)
    phone_number: str = Field(default=None, max_length=24)
    preferred_channel: str = Field(default=None, max_length=10)
    # Explicit WhatsApp consent. True records a consent timestamp; False opts
    # out immediately. None leaves the current setting untouched.
    whatsapp_opt_in: Optional[bool] = None


# --- app.py:2926-2994 ---
@router.post("/api/auth/profile/update")
def profile_update(req: ProfileUpdateRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    updates = []
    params = []
    if req.full_name is not None:
        updates.append("full_name = ?")
        params.append(req.full_name)
    if req.latitude is not None:
        updates.append("latitude = ?")
        params.append(req.latitude)
    if req.longitude is not None:
        updates.append("longitude = ?")
        params.append(req.longitude)
    if req.timezone is not None:
        updates.append("timezone = ?")
        params.append(req.timezone)
    if req.language is not None:
        updates.append("language = ?")
        params.append(req.language)
    if req.location_name is not None:
        updates.append("location_name = ?")
        params.append(req.location_name)
    new_phone = None  # track for the opt-in guard below
    if req.phone_number is not None:
        # Empty string clears the number (and any opt-in below); a non-empty
        # value must validate as E.164 before we store it.
        new_phone = _normalize_e164(req.phone_number) if req.phone_number.strip() else ""
        updates.append("phone_number = ?")
        params.append(new_phone)
    if req.preferred_channel is not None:
        updates.append("preferred_channel = ?")
        params.append(req.preferred_channel)
    if req.whatsapp_opt_in:
        # Can't consent to WhatsApp with no number on file — the number being
        # set in this same request counts.
        effective_phone = new_phone if new_phone is not None else user.get("phone_number")
        if not effective_phone:
            raise HTTPException(
                status_code=400,
                detail="Add a WhatsApp phone number before enabling WhatsApp delivery.",
            )
    if req.whatsapp_opt_in is not None:
        # Consent is a record: opting in stamps the moment; opting out clears it.
        updates.append("whatsapp_opt_in = ?")
        params.append(1 if req.whatsapp_opt_in else 0)
        updates.append("whatsapp_opt_in_at = ?")
        params.append(datetime.utcnow().isoformat() if req.whatsapp_opt_in else None)
    elif new_phone == "":
        # Clearing the phone in this request revokes any standing consent so we
        # never keep an opt-in flag with no number to deliver to.
        updates.append("whatsapp_opt_in = 0")
        updates.append("whatsapp_opt_in_at = NULL")

    if updates:
        params.append(user["id"])
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        conn = connect_db(DB_PATH)
        try:
            conn.execute(query, tuple(params))
            conn.commit()
        finally:
            conn.close()

    return {"status": "success"}


# --- app.py:3137-3177 ---
import base64
import random
import urllib.parse
import urllib.request

def _send_msg91_otp(phone_number: str, otp: str) -> bool:
    if not (MSG91_AUTH_KEY and MSG91_OTP_TEMPLATE_ID):
        logger.warning("MSG91 credentials not configured.")
        return False

    mobile = phone_number.replace("+", "").strip()
    params = {
        "template_id": MSG91_OTP_TEMPLATE_ID,
        "mobile": mobile,
        "otp": otp
    }
    url = "https://control.msg91.com/api/v5/otp?" + urllib.parse.urlencode(params)
    
    req = urllib.request.Request(url, method="POST")
    req.add_header("authkey", MSG91_AUTH_KEY)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("type") == "success":
                logger.info("MSG91 OTP sent successfully")
                return True
            else:
                logger.error("MSG91 OTP send failed: %s", res_data)
                return False
    except Exception as e:
        logger.error("Failed to send OTP via MSG91: %s", e)
        return False

def _send_otp_via_api(phone_number: str, otp: str, channel: str) -> bool:
    # MSG91 (SMS only) is the sole provider.
    if MSG91_AUTH_KEY and MSG91_OTP_TEMPLATE_ID:
        return _send_msg91_otp(phone_number, otp)

    logger.warning("MSG91 not configured. OTP logged to console: %s", otp)
    return False


# --- app.py:3179-3521 ---
@router.post("/api/auth/send-otp")
def auth_send_otp(req: SendOTPRequest):
    phone_number = req.phone_number.strip()
    # Basic validation and formatting for India (+91)
    if not phone_number.startswith("+"):
        clean_num = "".join(filter(str.isdigit, phone_number))
        if len(clean_num) == 10:
            phone_number = "+91" + clean_num
        else:
            raise HTTPException(status_code=400, detail="Invalid phone number format. Use country code, e.g. +91 98765 43210")
    
    otp = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
    
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO otp_verifications (phone_number, otp, channel, expires_at)
            VALUES (?, ?, ?, ?)
        """, (phone_number, otp, req.channel, expires_at))
        conn.commit()
    finally:
        conn.close()
        
    sent = _send_otp_via_api(phone_number, otp, req.channel)
    
    response_data = {"status": "success", "message": f"OTP sent via {req.channel}"}
    if ALLOW_MOCK_OAUTH or not sent:
        response_data["debug_otp"] = otp
        
    return response_data

@router.post("/api/auth/verify-otp")
def auth_verify_otp(req: VerifyOTPRequest):
    phone_number = req.phone_number.strip()
    if not phone_number.startswith("+"):
        clean_num = "".join(filter(str.isdigit, phone_number))
        if len(clean_num) == 10:
            phone_number = "+91" + clean_num
            
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT otp, channel, expires_at FROM otp_verifications
            WHERE phone_number = ?
        """, (phone_number,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=400, detail="No OTP requested for this phone number")
            
        stored_otp, channel, expires_str = row
        expires_at = datetime.fromisoformat(expires_str)
        
        if expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="OTP has expired. Please request a new one.")
            
        if stored_otp != req.otp.strip():
            raise HTTPException(status_code=401, detail="Invalid OTP")
            
        cursor.execute("DELETE FROM otp_verifications WHERE phone_number = ?", (phone_number,))
        
        cursor.execute("SELECT id, full_name, credit_balance FROM users WHERE phone_number = ?", (phone_number,))
        user_row = cursor.fetchone()
        
        if user_row:
            user_id, full_name, credit_balance = user_row
            cursor.execute("UPDATE users SET preferred_channel = ? WHERE id = ?", (channel, user_id))
        else:
            placeholder_email = f"phone_{phone_number.replace('+', '')}@phone.auth"
            cursor.execute("""
                INSERT INTO users (email, full_name, phone_number, preferred_channel, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
                VALUES (?, ?, ?, ?, ?, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
            """, (placeholder_email, f"Phone User {phone_number[-4:]}", phone_number, channel, SIGNUP_BONUS_CREDITS))
            user_id = cursor.lastrowid
            
            cursor.execute("""
                INSERT INTO user_authentications (user_id, provider, provider_user_id)
                VALUES (?, 'phone', ?)
            """, (user_id, phone_number))
            
            cursor.execute("UPDATE users SET referral_code = ? WHERE id = ?",
                           (_new_referral_code(cursor), user_id))
            cursor.execute("""
                INSERT INTO credit_logs (user_id, amount, action_type, details)
                VALUES (?, ?, 'signup_bonus', 'Phone signup credit bonus')
            """, (user_id, SIGNUP_BONUS_CREDITS))
            
            _apply_referral(cursor, user_id, req.referral_code)
            
        token = secrets.token_hex(32)
        expires_at_session = (datetime.utcnow() + timedelta(days=7)).isoformat()
        cursor.execute("""
            INSERT INTO sessions (session_token, user_id, expires_at)
            VALUES (?, ?, ?)
        """, (token, user_id, expires_at_session))
        
        conn.commit()
    finally:
        conn.close()
        
    return {
        "status": "success",
        "token": token,
        "user": get_user_by_session(token)
    }

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

@router.post("/api/auth/signup")
def auth_signup(req: SignupRequest):
    email = (req.email or "").strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")
    if len(req.password or "") < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        hashed = hash_password(req.password)
        # create user with the signup bonus credits (see config.SIGNUP_BONUS_CREDITS).
        # Rely on the UNIQUE(email) constraint rather than a racy check-then-insert.
        try:
            cursor.execute("""
                INSERT INTO users (email, password_hash, full_name, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
                VALUES (?, ?, ?, ?, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
            """, (email, hashed, req.full_name, SIGNUP_BONUS_CREDITS))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Email already registered")
        user_id = cursor.lastrowid

        # Assign a shareable referral code and log the signup bonus.
        cursor.execute("UPDATE users SET referral_code = ? WHERE id = ?",
                       (_new_referral_code(cursor), user_id))
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, 'signup_bonus', 'Initial registration credit bonus')
        """, (user_id, SIGNUP_BONUS_CREDITS))

        # Apply any referral the new user signed up with (credits both sides).
        _apply_referral(cursor, user_id, req.referral_code)

        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "message": "User registered successfully"}

@router.post("/api/auth/login")
def auth_login(req: LoginRequest):
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, full_name, credit_balance FROM users WHERE email = ?", (req.email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user_id, hashed, full_name, credit_balance = row
    if not hashed or not verify_password(req.password, hashed):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Opportunistically purge expired sessions (ISO-8601 strings sort correctly).
    cursor.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.utcnow().isoformat(),))

    # create session
    token = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    cursor.execute("""
        INSERT INTO sessions (session_token, user_id, expires_at)
        VALUES (?, ?, ?)
    """, (token, user_id, expires_at))
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "token": token,
        "user": get_user_by_session(token)
    }

def _verify_google_token(token: str):
    """Verify a Google ID token via Google's tokeninfo endpoint.

    Returns (email, name) derived from the *verified* token, or None on any
    failure. Confirms the token was issued for our client id (aud) and that the
    email is verified — so a token minted for some other app cannot be replayed.
    """
    if not GOOGLE_OAUTH_CLIENT_ID or not token:
        return None
    try:
        url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": token})
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if data.get("aud") != GOOGLE_OAUTH_CLIENT_ID:
        return None
    if str(data.get("email_verified")).lower() != "true":
        return None
    email = data.get("email")
    if not email:
        return None
    return email, data.get("name") or email.split("@")[0]


def _verify_facebook_token(token: str):
    """Verify a Facebook access token via the Graph API.

    debug_token confirms the token belongs to OUR app (and is valid); /me then
    yields the verified email. Returns (email, name) or None.
    """
    if not (FACEBOOK_APP_ID and FACEBOOK_APP_SECRET) or not token:
        return None
    try:
        app_token = f"{FACEBOOK_APP_ID}|{FACEBOOK_APP_SECRET}"
        dbg = "https://graph.facebook.com/debug_token?" + urllib.parse.urlencode(
            {"input_token": token, "access_token": app_token}
        )
        with urllib.request.urlopen(dbg, timeout=10) as r:
            info = json.loads(r.read().decode("utf-8")).get("data", {})
        if not info.get("is_valid") or str(info.get("app_id")) != str(FACEBOOK_APP_ID):
            return None
        me = "https://graph.facebook.com/me?" + urllib.parse.urlencode(
            {"fields": "id,name,email", "access_token": token}
        )
        with urllib.request.urlopen(me, timeout=10) as r:
            prof = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    email = prof.get("email")
    if not email:
        return None
    return email, prof.get("name") or email.split("@")[0]


def _mock_oauth_identity(req: "OAuthRequest"):
    """Dev-only fallback (config.ALLOW_MOCK_OAUTH). Trusts the supplied email but
    REFUSES to log into any pre-existing account that wasn't itself created via
    mock OAuth (accounts created here carry a 'mock-' provider prefix). This
    closes the hole where a real Google-created account (oauth_provider=
    'google', no password) could be hijacked by sending provider='google' with
    a bogus token while mock mode is on. Off by default."""
    email = (req.email or "").strip()
    if not email:
        return None
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT password_hash, oauth_provider FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    if row:
        password_hash, existing_provider = row
        if password_hash:
            return None  # real password account — never hijack via mock
        if not (existing_provider or "").startswith("mock-"):
            return None  # real (provider-verified) OAuth account — never hijack
    return email, req.name or email.split("@")[0]


@router.post("/api/auth/oauth")
def auth_oauth(req: OAuthRequest):
    """Social login. The identity (email) is taken ONLY from a provider-verified
    token, never from the client-supplied email, which closes the account-
    takeover hole. Unconfigured providers fail closed (unless the explicit
    dev-only mock mode is enabled)."""
    provider = (req.provider or "").lower()
    if provider == "google":
        identity = _verify_google_token(req.token)
    elif provider == "facebook":
        raise HTTPException(
            status_code=400,
            detail="Facebook login is no longer supported."
        )
    else:
        identity = None

    if identity is None and ALLOW_MOCK_OAUTH:
        identity = _mock_oauth_identity(req)
        if identity is not None:
            # Tag mock-created accounts so they can never shadow (or later be
            # confused with) accounts created via real provider verification.
            provider = f"mock-{provider}"

    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="OAuth verification failed or provider not configured.",
        )
    verified_email, verified_name = identity

    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, credit_balance FROM users WHERE email = ?", (verified_email,))
    row = cursor.fetchone()
    if row:
        user_id, full_name, credit_balance = row
    else:
        # Auto-signup with the signup bonus credits and preferences defaults
        cursor.execute("""
            INSERT INTO users (email, full_name, oauth_provider, oauth_id, credit_balance, latitude, longitude, timezone, language, wants_newsletter, location_name)
            VALUES (?, ?, ?, ?, ?, 13.0827, 80.2707, 'Asia/Kolkata', 'en', 1, 'Chennai, India')
        """, (verified_email, verified_name, provider, verified_email, SIGNUP_BONUS_CREDITS))
        user_id = cursor.lastrowid
        cursor.execute("UPDATE users SET referral_code = ? WHERE id = ?",
                       (_new_referral_code(cursor), user_id))
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, 'signup_bonus', 'OAuth signup credit bonus')
        """, (user_id, SIGNUP_BONUS_CREDITS))
        _apply_referral(cursor, user_id, req.referral_code)
        conn.commit()

    # create session
    token = secrets.token_hex(32)
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    cursor.execute("""
        INSERT INTO sessions (session_token, user_id, expires_at)
        VALUES (?, ?, ?)
    """, (token, user_id, expires_at))
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "token": token,
        "user": get_user_by_session(token)
    }

@router.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    if token:
        conn = connect_db(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
        conn.commit()
        conn.close()
    return {"status": "success"}


# --- app.py:3523-3529 ---
@router.get("/api/auth/me")
def auth_me(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


