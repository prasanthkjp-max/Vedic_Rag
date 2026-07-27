"""Billing domain: credit purchases, gift orders/redemption, and the Astro
Pass subscription, all via Razorpay (Orders + Subscriptions APIs).
"""
import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.core.config import (
    DB_PATH,
    PORTAL_BASE_URL,
    ALLOW_SIMULATED_PAYMENTS,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    RAZORPAY_ENABLED,
    RAZORPAY_PLAN_ID,
    SUBSCRIPTION_TOTAL_COUNT,
    SUBSCRIPTION_PRICE_PAISE,
    SUBSCRIPTION_REFILL_CREDITS,
    SUBSCRIPTION_PERIOD_DAYS,
    gst_breakdown,
    GIFT_SELF_REDEEM,
    GIFT_PDF_VOUCHER_PRICE_PAISE,
    GIFT_PDF_VOUCHER_CREDITS,
    BILLING_CURRENCY,
    CREDIT_PACKAGES,
    connect_db,
)
from src.api.deps import logger, get_user_by_session, _session_user_or_401, _safe_slug, Tier

router = APIRouter()


# --- app.py:998-1027 ---
class BuyCreditsRequest(BaseModel):
    amount: int

class CreateOrderRequest(BaseModel):
    amount: int  # credits == one of the advertised CREDIT_PACKAGES keys

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=256)

class CreateGiftOrderRequest(BaseModel):
    gift_type: Literal["credit_pack", "premium_pdf_voucher"]
    # Only meaningful for credit_pack (must be an advertised CREDIT_PACKAGES key);
    # ignored for premium_pdf_voucher, which is a fixed-price item.
    amount: int = 0

class BuyGiftRequest(CreateGiftOrderRequest):
    pass

class RedeemGiftRequest(BaseModel):
    code: str = Field(max_length=32)

class VerifySubscriptionRequest(BaseModel):
    razorpay_subscription_id: str = Field(max_length=64)
    razorpay_payment_id: str = Field(max_length=64)
    razorpay_signature: str = Field(max_length=256)

class SubscribeRequest(BaseModel):
    tier: Tier


# --- app.py:3531-4387 ---
def _require_simulated_payments():
    """Gate the legacy buy-credits shortcut to explicit local-dev simulation.

    Without this, buy-credits would hand out credits for free to anyone with a
    session. The real money path is Razorpay (create-order -> verify-payment /
    webhook); this endpoint exists only for local dev and tests.
    """
    if not ALLOW_SIMULATED_PAYMENTS:
        raise HTTPException(
            status_code=503,
            detail="Simulated payments are disabled. Use the Razorpay checkout flow.",
        )


def _require_razorpay_enabled():
    """Fail closed unless Razorpay credentials are configured."""
    if not RAZORPAY_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Payments are not configured on this server.",
        )


def _get_razorpay_client():
    """Lazily build a Razorpay client. Imported lazily so `import app` (and CI)
    don't hard-require the SDK when payments are turned off."""
    try:
        import razorpay
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Razorpay SDK not installed on the server.",
        )
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def _verify_payment_signature(order_id, payment_id, signature, secret=None):
    """Verify a Razorpay Checkout callback signature.

    Razorpay signs `<order_id>|<payment_id>` with HMAC-SHA256 keyed by the API
    secret. Constant-time compared so a wrong signature can't be timing-probed.
    """
    secret = secret if secret is not None else RAZORPAY_KEY_SECRET
    expected = hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _verify_subscription_signature(subscription_id, payment_id, signature, secret=None):
    """Verify a Razorpay Subscription Checkout callback signature.

    For subscriptions Razorpay signs `<payment_id>|<subscription_id>` — note the
    REVERSED order vs one-time orders (which sign order_id|payment_id). Keyed by
    the API secret, constant-time compared.
    """
    secret = secret if secret is not None else RAZORPAY_KEY_SECRET
    expected = hmac.new(
        secret.encode(), f"{payment_id}|{subscription_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _verify_webhook_signature(raw_body, signature, secret=None):
    """Verify a Razorpay webhook: HMAC-SHA256 of the RAW request body keyed by
    the webhook secret, compared constant-time against X-Razorpay-Signature."""
    secret = secret if secret is not None else RAZORPAY_WEBHOOK_SECRET
    if not secret:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _grant_credits_for_order(order_id, payment_id, gateway, expected_user_id=None):
    """Atomically flip a pending transaction to 'succeeded' and credit the user
    exactly once. Idempotent: the verify-payment callback and the webhook both
    call this for the same order, and whichever wins the status flip grants the
    credits; the loser is a no-op. Returns (granted: bool, credits: int|None).

    When `expected_user_id` is provided (user-facing verify path), the order is
    asserted to belong to that user before any credit is granted — an IDOR guard.
    The webhook path passes None (it has no session user; HMAC is the gate).
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute(
            "SELECT id, user_id, credits, status FROM transactions WHERE payment_intent_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return (False, None)
        txn_id, user_id, credits, status = row[0], row[1], row[2], row[3]
        if expected_user_id is not None and user_id != expected_user_id:
            conn.rollback()
            raise HTTPException(status_code=403, detail="Order does not belong to this account.")
        if status == "succeeded":
            conn.rollback()
            return (False, credits)  # already credited — idempotent no-op
        cursor.execute(
            "UPDATE transactions SET status='succeeded', gateway_transaction_id=? "
            "WHERE id=? AND status!='succeeded'",
            (payment_id, txn_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return (False, credits)  # lost the race; the winner credits
        cursor.execute(
            "INSERT INTO credit_logs (user_id, amount, action_type, details) "
            "VALUES (?, ?, 'purchase', ?)",
            (user_id, credits, f"Purchased {credits} credits via {gateway} ({payment_id})"),
        )
        cursor.execute(
            "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
            (credits, user_id),
        )
        conn.commit()
        return (True, credits)
    finally:
        conn.close()


# Unambiguous alphabet (no O/0/I/1/L) so a gift code can be read aloud / typed.
_GIFT_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _new_gift_code(cursor) -> str:
    """Generate a short, unguessable, human-typable gift code unique in
    gift_codes. Format: GIFT-XXXX-XXXX over the unambiguous alphabet."""
    for _ in range(20):
        body = "".join(secrets.choice(_GIFT_CODE_ALPHABET) for _ in range(8))
        code = f"GIFT-{body[:4]}-{body[4:]}"
        exists = cursor.execute("SELECT 1 FROM gift_codes WHERE code = ?", (code,)).fetchone()
        if not exists:
            return code
    # Astronomically unlikely; fall back to a longer random token.
    return "GIFT-" + secrets.token_hex(8).upper()


def _grant_gift_for_order(order_id, payment_id, gateway, expected_user_id=None):
    """Atomically flip a pending gift order to 'succeeded' and mint its single
    redemption code exactly once. Idempotent: verify-gift-payment and the webhook
    both call this; whichever wins the status flip mints the code, and a later
    call returns the SAME existing code (so the buyer's confirmation still shows
    it). Returns (granted: bool, info: dict|None) where info carries the code.

    When `expected_user_id` is set (user-facing verify path), the order is
    asserted to belong to that user — an IDOR guard.
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute(
            "SELECT id, purchaser_user_id, gift_type, amount, status FROM gift_orders "
            "WHERE payment_intent_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return (False, None)
        go_id, purchaser_id, gift_type, amount, status = row
        if expected_user_id is not None and purchaser_id != expected_user_id:
            conn.rollback()
            raise HTTPException(status_code=403, detail="Gift order does not belong to this account.")
        if status == "succeeded":
            # Already granted — return the existing code (idempotent no-op).
            existing = cursor.execute(
                "SELECT code FROM gift_codes WHERE order_id = ?", (go_id,)
            ).fetchone()
            conn.rollback()
            return (False, {"code": existing[0] if existing else None,
                            "gift_type": gift_type, "amount": amount})
        cursor.execute(
            "UPDATE gift_orders SET status = 'succeeded' WHERE id = ? AND status != 'succeeded'",
            (go_id,),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return (False, None)  # lost the race; winner mints the code
        code = _new_gift_code(cursor)
        cursor.execute(
            "INSERT INTO gift_codes (code, order_id) VALUES (?, ?)",
            (code, go_id),
        )
        conn.commit()
        return (True, {"code": code, "gift_type": gift_type, "amount": amount})
    finally:
        conn.close()


def _apply_subscription_charge(subscription_id, payment_id, expected_user_id=None):
    """Activate/renew an Astro Pass on a successful Razorpay charge, exactly once.

    Idempotent on `payment_id` via the transactions UNIQUE key: the verify
    callback (first charge) and the `subscription.charged` webhook (renewals)
    both call this; whichever records the payment first extends the access
    window by SUBSCRIPTION_PERIOD_DAYS and grants the per-cycle refill. Returns
    (applied: bool, user_id: int|None).

    When `expected_user_id` is provided (user-facing verify path), the
    subscription is asserted to belong to that user — an IDOR guard. The webhook
    path passes None (it has no session user; HMAC is the gate).
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        sub = cursor.execute(
            "SELECT user_id, current_period_end FROM subscriptions "
            "WHERE platform_subscription_id = ?",
            (subscription_id,),
        ).fetchone()
        if sub is None:
            conn.rollback()
            return (False, None)
        user_id, period_end_str = sub[0], sub[1]
        if expected_user_id is not None and user_id != expected_user_id:
            conn.rollback()
            raise HTTPException(status_code=403, detail="Subscription does not belong to this account.")
        # Idempotency: a payment we've already booked is a no-op (webhook retry
        # or callback+webhook race). INSERT fails on the UNIQUE payment id.
        try:
            cursor.execute(
                "INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits) "
                "VALUES (?, ?, ?, ?, 'succeeded', 'razorpay', ?)",
                (user_id, payment_id, SUBSCRIPTION_PRICE_PAISE, BILLING_CURRENCY, SUBSCRIPTION_REFILL_CREDITS),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return (False, user_id)
        # Extend from the later of now / existing period end so an early renewal
        # never shortens access.
        now = datetime.utcnow()
        try:
            base = max(now, datetime.fromisoformat(period_end_str)) if period_end_str else now
        except (ValueError, TypeError):
            base = now
        new_period_end = (base + timedelta(days=SUBSCRIPTION_PERIOD_DAYS)).isoformat()
        cursor.execute(
            "UPDATE subscriptions SET status='active', current_period_end=?, updated_at=? "
            "WHERE platform_subscription_id=?",
            (new_period_end, now.isoformat(), subscription_id),
        )
        if SUBSCRIPTION_REFILL_CREDITS:
            cursor.execute(
                "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
                (SUBSCRIPTION_REFILL_CREDITS, user_id),
            )
            cursor.execute(
                "INSERT INTO credit_logs (user_id, amount, action_type, details) "
                "VALUES (?, ?, 'subscription_bonus', ?)",
                (user_id, SUBSCRIPTION_REFILL_CREDITS, f"Astro Pass charge ({payment_id})"),
            )
        conn.commit()
        return (True, user_id)
    finally:
        conn.close()


def _deactivate_subscription(subscription_id, status):
    """Mark a Razorpay-backed subscription terminated (cancelled/halted/completed).

    get_user_by_session only treats status='active' (and unexpired) as a live
    pass, so any non-active status revokes access at the next request.
    """
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET status=?, updated_at=? WHERE platform_subscription_id=?",
            (status, datetime.utcnow().isoformat(), subscription_id),
        )
        conn.commit()
    finally:
        conn.close()


@router.post("/api/billing/buy-credits")
def buy_credits(req: BuyCreditsRequest, request: Request):
    """Legacy instant-grant path — local dev / tests only (simulated payments)."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_simulated_payments()

    # Only the advertised packages may be purchased — an arbitrary client
    # integer must not set its own credit amount (or a negative one). The packs
    # and currency live in config.py (CREDIT_PACKAGES maps credits -> price in
    # the smallest currency unit, e.g. paise for INR).
    if req.amount not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown credit package: {req.amount}")

    payment_intent = "pi_" + secrets.token_hex(16)
    cents = CREDIT_PACKAGES[req.amount]

    # Log the transaction and grant the credits in ONE transaction so a crash
    # cannot leave a paid-but-uncredited (or credited-but-unlogged) record.
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits)
            VALUES (?, ?, ?, ?, 'succeeded', 'simulated', ?)
        """, (user["id"], payment_intent, cents, BILLING_CURRENCY, req.amount))
        cursor.execute("""
            INSERT INTO credit_logs (user_id, amount, action_type, details)
            VALUES (?, ?, 'purchase', ?)
        """, (user["id"], req.amount, f"Purchased {req.amount} credits via simulated payment"))
        cursor.execute("UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
                       (req.amount, user["id"]))
        conn.commit()
    finally:
        conn.close()

    return {"status": "success", "added_credits": req.amount}


@router.post("/api/billing/create-order")
def create_order(req: CreateOrderRequest, request: Request):
    """Create a Razorpay Order for a credit pack and record it as pending.

    The customer pays the GST-INCLUSIVE pack price; the order amount sent to
    Razorpay is exactly that paise value. Returns the order id, public key, and
    GST breakdown so the frontend can open Checkout and show the tax split.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if req.amount not in CREDIT_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Unknown credit package: {req.amount}")

    credits = req.amount
    gross_paise = CREDIT_PACKAGES[credits]
    client = _get_razorpay_client()
    try:
        order = client.order.create({
            "amount": gross_paise,
            "currency": BILLING_CURRENCY,
            "receipt": f"u{user['id']}-{secrets.token_hex(6)}",
            "notes": {"user_id": str(user["id"]), "credits": str(credits)},
        })
    except Exception as e:
        logger.error("Razorpay order creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not create payment order.")

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits)
            VALUES (?, ?, ?, ?, 'created', 'razorpay', ?)
        """, (user["id"], order["id"], gross_paise, BILLING_CURRENCY, credits))
        conn.commit()
    finally:
        conn.close()

    gst = gst_breakdown(gross_paise)
    return {
        "order_id": order["id"],
        "key_id": RAZORPAY_KEY_ID,
        "amount": gross_paise,
        "currency": BILLING_CURRENCY,
        "credits": credits,
        "gst": gst,  # paise: {gross, base, gst, rate}
        "prefill": {"name": user.get("full_name") or "", "email": user.get("email") or "", "contact": user.get("phone_number") or ""},
    }


@router.post("/api/billing/verify-payment")
def verify_payment(req: VerifyPaymentRequest, request: Request):
    """Verify a Razorpay Checkout callback signature and grant credits.

    This is the fast, user-facing confirmation. The webhook is the authoritative
    backstop; both funnel through the idempotent grant so credits land exactly
    once even if both fire.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if not _verify_payment_signature(
        req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature.")

    granted, credits = _grant_credits_for_order(
        req.razorpay_order_id, req.razorpay_payment_id, "razorpay",
        expected_user_id=user["id"],
    )
    if credits is None:
        raise HTTPException(status_code=404, detail="Unknown order.")
    return {"status": "success", "credits": credits, "newly_granted": granted}


# ── Gift a reading ──────────────────────────────────────────────────────────
# A gift is a paid, single-use code the buyer shares. Redeeming it grants the
# recipient credits (a credit pack, or exactly one premium-report's worth). The
# purchase flow mirrors credit packs EXACTLY: Razorpay order -> verify + webhook
# both converge on the idempotent _grant_gift_for_order.

def _gift_price_and_credits(gift_type: str, amount: int):
    """Resolve a gift's GST-inclusive price (paise) and the credits it grants.
    Rejects a client-chosen price — only advertised packs / the fixed voucher."""
    if gift_type == "credit_pack":
        if amount not in CREDIT_PACKAGES:
            raise HTTPException(status_code=400, detail=f"Unknown credit package: {amount}")
        return CREDIT_PACKAGES[amount], amount
    if gift_type == "premium_pdf_voucher":
        return GIFT_PDF_VOUCHER_PRICE_PAISE, GIFT_PDF_VOUCHER_CREDITS
    raise HTTPException(status_code=400, detail="Unknown gift type.")


@router.post("/api/billing/create-gift-order")
def create_gift_order(req: CreateGiftOrderRequest, request: Request):
    """Create a Razorpay order for a gift and record it pending. Returns the
    order id, public key, and GST breakdown (mirrors create-order)."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    gross_paise, credits = _gift_price_and_credits(req.gift_type, req.amount)
    client = _get_razorpay_client()
    try:
        order = client.order.create({
            "amount": gross_paise,
            "currency": BILLING_CURRENCY,
            "receipt": f"gift-u{user['id']}-{secrets.token_hex(6)}",
            "notes": {"user_id": str(user["id"]), "gift_type": req.gift_type, "credits": str(credits)},
        })
    except Exception as e:
        logger.error("Razorpay gift order creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not create gift order.")

    conn = connect_db(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO gift_orders (purchaser_user_id, gift_type, amount, payment_intent_id, status) "
            "VALUES (?, ?, ?, ?, 'created')",
            (user["id"], req.gift_type, credits, order["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "order_id": order["id"],
        "key_id": RAZORPAY_KEY_ID,
        "amount": gross_paise,
        "currency": BILLING_CURRENCY,
        "gift_type": req.gift_type,
        "credits": credits,
        "gst": gst_breakdown(gross_paise),
        "prefill": {"name": user.get("full_name") or "", "email": user.get("email") or "", "contact": user.get("phone_number") or ""},
    }


@router.post("/api/billing/verify-gift-payment")
def verify_gift_payment(req: VerifyPaymentRequest, request: Request):
    """Verify a gift-order Checkout signature and mint the gift code (idempotent
    with the webhook via _grant_gift_for_order)."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if not _verify_payment_signature(
        req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Invalid payment signature.")

    granted, info = _grant_gift_for_order(
        req.razorpay_order_id, req.razorpay_payment_id, "razorpay",
        expected_user_id=user["id"],
    )
    if info is None:
        raise HTTPException(status_code=404, detail="Unknown gift order.")
    return {"status": "success", "newly_granted": granted,
            "code": info["code"], "gift_type": info["gift_type"], "credits": info["amount"],
            "share_url": f"{PORTAL_BASE_URL}/gift/{info['code']}"}


@router.post("/api/billing/buy-gift")
def buy_gift(req: BuyGiftRequest, request: Request):
    """Legacy instant gift purchase — local dev / tests only (simulated)."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_simulated_payments()

    gross_paise, credits = _gift_price_and_credits(req.gift_type, req.amount)
    payment_intent = "gi_" + secrets.token_hex(16)
    conn = connect_db(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO gift_orders (purchaser_user_id, gift_type, amount, payment_intent_id, status) "
            "VALUES (?, ?, ?, ?, 'created')",
            (user["id"], req.gift_type, credits, payment_intent),
        )
        conn.commit()
    finally:
        conn.close()
    granted, info = _grant_gift_for_order(payment_intent, payment_intent, "simulated",
                                          expected_user_id=user["id"])
    return {"status": "success", "code": info["code"], "gift_type": info["gift_type"],
            "credits": info["amount"], "share_url": f"{PORTAL_BASE_URL}/gift/{info['code']}"}


@router.post("/api/billing/redeem-gift")
def redeem_gift(req: RedeemGiftRequest, request: Request):
    """Redeem a gift code once, crediting the redeemer. Atomic single-use: the
    conditional UPDATE (redeemed_by_user_id IS NULL) is the race guard — no
    read-then-write. A purchaser cannot redeem their own code unless
    GIFT_SELF_REDEEM is enabled."""
    user = _session_user_or_401(request)
    code = (req.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Enter a gift code.")

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute(
            "SELECT gc.id, gc.redeemed_by_user_id, go.purchaser_user_id, go.status, go.amount "
            "FROM gift_codes gc JOIN gift_orders go ON gc.order_id = go.id "
            "WHERE gc.code = ?",
            (code,),
        ).fetchone()
        if row is None:
            conn.rollback()
            raise HTTPException(status_code=404, detail="That gift code was not found.")
        gc_id, redeemed_by, purchaser_id, order_status, amount = row
        if order_status != "succeeded":
            conn.rollback()
            raise HTTPException(status_code=400, detail="This gift is not active yet.")
        if redeemed_by is not None:
            conn.rollback()
            raise HTTPException(status_code=409, detail="This gift code has already been redeemed.")
        if purchaser_id == user["id"] and not GIFT_SELF_REDEEM:
            conn.rollback()
            raise HTTPException(status_code=403, detail="You cannot redeem your own gift — share it with someone else.")
        # Atomic claim: only succeeds if still unredeemed (race guard).
        cursor.execute(
            "UPDATE gift_codes SET redeemed_by_user_id = ?, redeemed_at = ? "
            "WHERE id = ? AND redeemed_by_user_id IS NULL",
            (user["id"], datetime.utcnow().isoformat(), gc_id),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            raise HTTPException(status_code=409, detail="This gift code has already been redeemed.")
        cursor.execute(
            "UPDATE users SET credit_balance = credit_balance + ? WHERE id = ?",
            (amount, user["id"]),
        )
        cursor.execute(
            "INSERT INTO credit_logs (user_id, amount, action_type, details) "
            "VALUES (?, ?, 'gift_redeem', ?)",
            (user["id"], amount, f"Redeemed gift code {code}"),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "success", "credits_added": amount}


@router.get("/gift/{code}")
def gift_landing(code: str):
    """Public gift landing page. Routes the recipient to sign in / sign up and
    then auto-redeem the code (the SPA reads ?gift= and calls redeem-gift)."""
    safe_code = _safe_slug(code, fallback="")[:32].upper()
    target = f"{PORTAL_BASE_URL}/?gift={safe_code}"
    return HTMLResponse(
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<meta http-equiv='refresh' content='0; url={target}'>"
        "<title>Your Vedic reading gift</title></head>"
        "<body style='font-family:sans-serif;background:#12101c;color:#eee;display:flex;"
        "align-items:center;justify-content:center;height:100vh;text-align:center'>"
        "<div><h2>🎁 You've received a Vedic reading gift!</h2>"
        f"<p>Redeeming code <strong style='color:#d4af37'>{safe_code}</strong>…</p>"
        f"<p><a style='color:#d4af37' href='{target}'>Continue to the portal</a></p></div>"
        "</body></html>"
    )


@router.post("/api/billing/create-subscription")
def create_subscription(request: Request):
    """Create a Razorpay Subscription for the Astro Pass and record it pending.

    Needs a Plan (RAZORPAY_PLAN_ID) created once in the Razorpay dashboard for
    the ₹99/mo pass; fails closed without it. Returns the subscription id +
    public key so the frontend can open Checkout to authorise the mandate.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()
    if not RAZORPAY_PLAN_ID:
        raise HTTPException(status_code=503, detail="Subscriptions are not configured on this server.")

    client = _get_razorpay_client()
    try:
        sub = client.subscription.create({
            "plan_id": RAZORPAY_PLAN_ID,
            "total_count": SUBSCRIPTION_TOTAL_COUNT,
            "customer_notify": 1,
            "notes": {"user_id": str(user["id"])},
        })
    except Exception as e:
        logger.error("Razorpay subscription creation failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not create subscription.")

    # Record (or replace) a pending subscription keyed by the Razorpay id. It
    # only becomes 'active' once a charge is confirmed (verify / webhook).
    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user["id"],))
        cursor.execute(
            "INSERT INTO subscriptions (user_id, status, tier, current_period_end, platform, platform_subscription_id, billing_interval, price_cents) "
            "VALUES (?, 'created', 'astro', ?, 'razorpay', ?, 'monthly', ?)",
            (user["id"], datetime.utcnow().isoformat(), sub["id"], SUBSCRIPTION_PRICE_PAISE),
        )
        conn.commit()
    finally:
        conn.close()

    gst = gst_breakdown(SUBSCRIPTION_PRICE_PAISE)
    return {
        "subscription_id": sub["id"],
        "key_id": RAZORPAY_KEY_ID,
        "amount": SUBSCRIPTION_PRICE_PAISE,
        "currency": BILLING_CURRENCY,
        "tier": "astro",
        "gst": gst,
        "prefill": {"name": user.get("full_name") or "", "email": user.get("email") or "", "contact": user.get("phone_number") or ""},
    }


@router.post("/api/billing/verify-subscription")
def verify_subscription(req: VerifySubscriptionRequest, request: Request):
    """Verify the subscription Checkout callback and activate the Astro Pass.

    The webhook (`subscription.charged`) is the authoritative renewal path; this
    is the fast first-charge confirmation. Both funnel through the idempotent
    _apply_subscription_charge so the pass activates exactly once.
    """
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    _require_razorpay_enabled()

    if not _verify_subscription_signature(
        req.razorpay_subscription_id, req.razorpay_payment_id, req.razorpay_signature
    ):
        raise HTTPException(status_code=400, detail="Invalid subscription signature.")

    applied, uid = _apply_subscription_charge(
        req.razorpay_subscription_id, req.razorpay_payment_id,
        expected_user_id=user["id"],
    )
    if uid is None:
        raise HTTPException(status_code=404, detail="Unknown subscription.")
    return {"status": "success", "tier": "astro", "newly_activated": applied}


@router.post("/api/billing/webhook")
async def razorpay_webhook(request: Request):
    """Authoritative server-to-server credit grant on payment.captured.

    Verifies the raw-body HMAC against RAZORPAY_WEBHOOK_SECRET, then grants
    idempotently. Always 200s on a verified-but-already-processed event so
    Razorpay stops retrying.
    """
    _require_razorpay_enabled()
    raw = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    if not _verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed webhook body.")

    event_type = event.get("event")
    payload = event.get("payload", {})

    if event_type == "payment.captured":
        entity = payload.get("payment", {}).get("entity", {})
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        # Subscription charges also arrive as payment.captured but carry no
        # order_id — skip those here; subscription.charged handles them.
        if order_id and payment_id:
            # An order id belongs to EITHER a credit pack (transactions) or a
            # gift (gift_orders); each grant is a no-op if the id isn't its own,
            # so calling both is safe and idempotent.
            _grant_credits_for_order(order_id, payment_id, "razorpay")
            _grant_gift_for_order(order_id, payment_id, "razorpay")

    elif event_type == "subscription.charged":
        sub_id = payload.get("subscription", {}).get("entity", {}).get("id")
        payment_id = payload.get("payment", {}).get("entity", {}).get("id")
        if sub_id and payment_id:
            _apply_subscription_charge(sub_id, payment_id)

    elif event_type in ("subscription.cancelled", "subscription.halted", "subscription.completed"):
        sub_id = payload.get("subscription", {}).get("entity", {}).get("id")
        if sub_id:
            _deactivate_subscription(sub_id, event_type.split(".", 1)[1])

    return {"status": "ok"}

@router.post("/api/billing/subscribe")
def billing_subscribe(req: SubscribeRequest, request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Recurring subscription billing via Razorpay is deferred (Phase 2 ships
    # one-time credit packs only); the Astro Pass remains simulation-gated.
    _require_simulated_payments()

    sub_id = "sub_" + secrets.token_hex(16)
    period_end = (datetime.utcnow() + timedelta(days=30)).isoformat()
    
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # Update or insert subscription
    cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user["id"],))
    # Write platform_subscription_id (the column the Razorpay path uses) so the
    # active-subscription check and any reconciliation see a consistent shape,
    # and use the config-driven refill amount instead of a hardcoded 5000.
    cursor.execute("""
        INSERT INTO subscriptions (user_id, platform_subscription_id, platform, status, tier, current_period_end)
        VALUES (?, ?, 'simulated', 'active', ?, ?)
    """, (user["id"], sub_id, req.tier, period_end))

    # Grant refill credits
    cursor.execute("""
        UPDATE users
        SET credit_balance = credit_balance + ?
        WHERE id = ?
    """, (SUBSCRIPTION_REFILL_CREDITS, user["id"]))
    cursor.execute("""
        INSERT INTO credit_logs (user_id, amount, action_type, details)
        VALUES (?, ?, 'subscription_bonus', ?)
    """, (user["id"], SUBSCRIPTION_REFILL_CREDITS, f"Credits added for {req.tier} subscription"))
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "tier": req.tier}

@router.post("/api/billing/cancel-subscription")
def billing_cancel(request: Request):
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # For a Razorpay-backed pass, cancel at the END of the paid cycle so the user
    # keeps access they've paid for; Razorpay then fires subscription.cancelled
    # at period end, which flips the local status. The pass stays active here
    # until then (we only flag cancel_at_period_end). A simulated/legacy sub has
    # no platform id, so just mark it cancelled immediately.
    row = cursor.execute(
        "SELECT platform_subscription_id FROM subscriptions WHERE user_id = ?",
        (user["id"],),
    ).fetchone()
    platform_sub_id = row[0] if row else None

    cancelled_at_cycle_end = False
    if platform_sub_id and RAZORPAY_ENABLED:
        try:
            _get_razorpay_client().subscription.cancel(
                platform_sub_id, {"cancel_at_cycle_end": 1}
            )
            cancelled_at_cycle_end = True
        except Exception as e:
            logger.error("Razorpay subscription cancel failed: %s", e)
            conn.close()
            raise HTTPException(status_code=502, detail="Could not cancel subscription.")

    if cancelled_at_cycle_end:
        cursor.execute(
            "UPDATE subscriptions SET cancel_at_period_end = 1, updated_at = ? WHERE user_id = ?",
            (datetime.utcnow().isoformat(), user["id"]),
        )
    else:
        cursor.execute("UPDATE subscriptions SET status = 'cancelled' WHERE user_id = ?", (user["id"],))
    conn.commit()
    conn.close()
    return {"status": "success", "cancel_at_period_end": cancelled_at_cycle_end}


@router.get("/api/billing/usage")
def billing_usage(request: Request):
    """Per-user usage summary for the profile dashboard: current balance, credits
    spent this calendar month (debits are stored as negative credit_logs rows),
    subscription state, and the most recent credit-ledger activity."""
    token = request.headers.get("x-session-token") or request.cookies.get("session_token")
    user = get_user_by_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    conn = connect_db(DB_PATH)
    try:
        cursor = conn.cursor()
        # Spent this month = sum of debits (negative amounts) since the 1st.
        cursor.execute(
            "SELECT COALESCE(SUM(-amount), 0) FROM credit_logs "
            "WHERE user_id = ? AND amount < 0 AND created_at >= ?",
            (user["id"], month_start),
        )
        used_this_month = cursor.fetchone()[0]
        cursor.execute(
            "SELECT amount, action_type, details, created_at FROM credit_logs "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 8",
            (user["id"],),
        )
        recent = [
            {"amount": r[0], "action_type": r[1], "details": r[2], "created_at": r[3]}
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()

    return {
        "credits_remaining": user["credit_balance"],
        "credits_used_this_month": used_this_month,
        "subscription_active": user.get("subscription_active", False),
        "subscription_tier": user.get("subscription_tier"),
        "recent_activity": recent,
    }


