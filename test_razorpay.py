"""
Deterministic, no-server/no-browser unit tests for the Razorpay payment layer.

Covers the security- and money-critical pure logic that must never silently
regress: the GST-inclusive split (base + gst == gross, exactly), the Razorpay
Checkout payment-signature verification, and the webhook-signature
verification. None of these touch the network or the Razorpay SDK — the
verifiers are plain HMAC-SHA256 and accept an explicit secret.

Runs standalone (`python3 test_razorpay.py`, exit 0/1) and in CI. Uses an
isolated temp DB so importing app never touches a real database.
"""
import os
import sys
import json
import hmac
import hashlib
import secrets
import tempfile

# Isolate the DB BEFORE importing app/config (DB_PATH is captured at import).
_TMP = tempfile.mkdtemp(prefix="vedic_razorpay_")
os.environ["VEDIC_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ.setdefault("VEDIC_LOG_LEVEL", "ERROR")

import app
from config import gst_breakdown, CREDIT_PACKAGES, GST_RATE

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


# ── GST-inclusive breakdown ─────────────────────────────────────────────────
for credits, gross in CREDIT_PACKAGES.items():
    b = gst_breakdown(gross)
    check(f"gst[{credits}]: base + gst == gross (no rounding drift)",
          b["base"] + b["gst"] == gross)
    check(f"gst[{credits}]: base == round(gross / (1+rate))",
          b["base"] == round(gross / (1 + GST_RATE)))
    check(f"gst[{credits}]: gross is unchanged (customer pays listed price)",
          b["gross"] == gross)

# ₹29 inclusive of 18% GST -> base ₹24.58, gst ₹4.42 (2458 + 442 == 2900 paise)
b29 = gst_breakdown(2900, 0.18)
check("gst: ₹29 splits to 2458 base + 442 gst", b29["base"] == 2458 and b29["gst"] == 442)


# ── Razorpay Checkout payment signature ─────────────────────────────────────
SECRET = "test_secret_key"
order_id = "order_ABC123"
payment_id = "pay_XYZ789"
good_sig = hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(),
                    hashlib.sha256).hexdigest()

check("payment sig: valid signature verifies",
      app._verify_payment_signature(order_id, payment_id, good_sig, secret=SECRET) is True)
check("payment sig: tampered payment_id rejected",
      app._verify_payment_signature(order_id, "pay_TAMPERED", good_sig, secret=SECRET) is False)
check("payment sig: tampered order_id rejected",
      app._verify_payment_signature("order_TAMPERED", payment_id, good_sig, secret=SECRET) is False)
check("payment sig: empty signature rejected",
      app._verify_payment_signature(order_id, payment_id, "", secret=SECRET) is False)
check("payment sig: wrong secret rejected",
      app._verify_payment_signature(order_id, payment_id, good_sig, secret="other") is False)


# ── Razorpay webhook signature ──────────────────────────────────────────────
WHSECRET = "test_webhook_secret"
body = json.dumps({
    "event": "payment.captured",
    "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}},
}).encode()
wh_sig = hmac.new(WHSECRET.encode(), body, hashlib.sha256).hexdigest()

check("webhook sig: valid signature verifies",
      app._verify_webhook_signature(body, wh_sig, secret=WHSECRET) is True)
check("webhook sig: tampered body rejected",
      app._verify_webhook_signature(body + b" ", wh_sig, secret=WHSECRET) is False)
check("webhook sig: empty secret rejected (fail closed)",
      app._verify_webhook_signature(body, wh_sig, secret="") is False)


# ── Razorpay subscription signature (reversed order: payment_id|subscription_id) ──
sub_id = "sub_ABC123"
# Correct subscription signing: payment_id|subscription_id.
sub_sig = hmac.new(SECRET.encode(), f"{payment_id}|{sub_id}".encode(), hashlib.sha256).hexdigest()
check("sub sig: valid signature verifies",
      app._verify_subscription_signature(sub_id, payment_id, sub_sig, secret=SECRET) is True)
check("sub sig: tampered subscription_id rejected",
      app._verify_subscription_signature("sub_TAMPERED", payment_id, sub_sig, secret=SECRET) is False)
# A signature built in the *order* convention (order_id|payment_id) must NOT pass
# the subscription verifier — guards against copy-pasting the wrong field order.
order_convention_sig = hmac.new(SECRET.encode(), f"{sub_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
check("sub sig: order-convention signature rejected",
      app._verify_subscription_signature(sub_id, payment_id, order_convention_sig, secret=SECRET) is False)


# ── Gift orders: idempotent grant, single-use redemption, refund path ────────
import datetime
from fastapi import HTTPException
from fastapi.testclient import TestClient
from config import connect_db

_client = TestClient(app.app)


def _mk_user(email, balance=0):
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO users (email, credit_balance) VALUES (?, ?)", (email, balance))
    uid = cur.lastrowid
    conn.commit()
    conn.close()
    return uid


def _mk_session(uid):
    tok = secrets.token_hex(16)
    conn = connect_db()
    exp = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?, ?, ?)",
                 (tok, uid, exp))
    conn.commit()
    conn.close()
    return tok


def _balance(uid):
    conn = connect_db()
    row = conn.execute("SELECT credit_balance FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return row[0]


def _gift_code_count(order_pi):
    conn = connect_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM gift_codes gc JOIN gift_orders go ON gc.order_id = go.id "
        "WHERE go.payment_intent_id = ?", (order_pi,)
    ).fetchone()
    conn.close()
    return row[0]


# Seed a purchaser + a pending gift order (a 500-credit pack gift).
_buyer = _mk_user("gift_buyer@test", 0)
_conn = connect_db()
_conn.execute(
    "INSERT INTO gift_orders (purchaser_user_id, gift_type, amount, payment_intent_id, status) "
    "VALUES (?, 'credit_pack', 500, 'order_GIFT1', 'created')",
    (_buyer,),
)
_conn.commit()
_conn.close()

# Double-webhook idempotency: two grants mint exactly one code, same value.
_g1, _info1 = app._grant_gift_for_order("order_GIFT1", "pay_g1", "razorpay")
_g2, _info2 = app._grant_gift_for_order("order_GIFT1", "pay_g1", "razorpay")
check("gift: first grant mints a code", _g1 is True and _info1 and _info1["code"])
check("gift: second grant is a no-op", _g2 is False)
check("gift: idempotent — same code returned", _info1["code"] == _info2["code"])
check("gift: exactly one code row exists", _gift_code_count("order_GIFT1") == 1)

_gift_code = _info1["code"]

# Self-redeem is forbidden (GIFT_SELF_REDEEM=0 by default): buyer can't redeem.
_buyer_sess = _mk_session(_buyer)
_r_self = _client.post("/api/billing/redeem-gift", headers={"x-session-token": _buyer_sess},
                       json={"code": _gift_code})
check("gift: purchaser cannot redeem own code (403)", _r_self.status_code == 403)
check("gift: buyer balance unchanged after self-redeem attempt", _balance(_buyer) == 0)

# A different user redeems once (200, credited), second time fails (409).
_redeemer = _mk_user("gift_redeemer@test", 0)
_red_sess = _mk_session(_redeemer)
_r1 = _client.post("/api/billing/redeem-gift", headers={"x-session-token": _red_sess},
                   json={"code": _gift_code})
check("gift: first redemption succeeds (200)", _r1.status_code == 200)
check("gift: redeemer credited 500", _balance(_redeemer) == 500)
_r2 = _client.post("/api/billing/redeem-gift", headers={"x-session-token": _red_sess},
                   json={"code": _gift_code})
check("gift: second redemption fails (409)", _r2.status_code == 409)
check("gift: redeemer not double-credited", _balance(_redeemer) == 500)

# Unknown code -> 404.
_r404 = _client.post("/api/billing/redeem-gift", headers={"x-session-token": _red_sess},
                     json={"code": "GIFT-ZZZZ-ZZZZ"})
check("gift: unknown code rejected (404)", _r404.status_code == 404)

# Grant on a non-existent order id is a clean no-op (not this table's order).
_gx, _infox = app._grant_gift_for_order("order_NOT_A_GIFT", "pay_x", "razorpay")
check("gift: grant on unknown order id is a no-op", _gx is False and _infox is None)


# ── Premium report failure path refunds the debit ───────────────────────────
# _build_premium_report catches ANY failure, marks the report failed, and
# refunds the charged credits through the same ledger. With no OPENROUTER key
# configured in the test env, chapter generation raises deterministically.
_rep_user = _mk_user("report_fail@test", 300)
_report_id = "testreport123"
_conn = connect_db()
_conn.execute(
    "INSERT INTO pdf_reports (id, user_id, status, client_name, place_name) "
    "VALUES (?, ?, 'pending', 'Tester', 'Chennai')",
    (_report_id, _rep_user),
)
_conn.commit()
_conn.close()

# Simulate the state after a 150-credit debit, then run the (failing) builder.
app.debit_user_credits(_rep_user, -150, "download_pdf_premium", "debit for test")
_balance_after_debit = _balance(_rep_user)
app._build_premium_report(
    _report_id, _rep_user, 150, {"metadata": {"latitude": 13.0, "longitude": 80.0},
                                 "panchangam": {}, "placements": {}},
    "Tester", "Chennai", "south", "en", None, False,
)
_conn = connect_db()
_row = _conn.execute("SELECT status FROM pdf_reports WHERE id = ?", (_report_id,)).fetchone()
_conn.close()
check("report: failed generation marks status 'failed'", _row and _row[0] == "failed")
check("report: failed generation refunds the debit",
      _balance(_rep_user) == _balance_after_debit + 150)


# ── WhatsApp webhook: signature verification + STOP auto opt-out ─────────────
from whatsapp_sender import verify_whatsapp_signature
import config as _config

# Point the module + config at a known webhook secret for this test.
_WA_SECRET = "wa_test_secret"
_config.WHATSAPP_WEBHOOK_SECRET = _WA_SECRET
import whatsapp_sender as _wa
_wa.WHATSAPP_WEBHOOK_SECRET = _WA_SECRET

_wa_body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
    {"type": "text", "from": "919876500000", "text": {"body": "STOP"}}]}}]}]}).encode()
_wa_sig = "sha256=" + hmac.new(_WA_SECRET.encode(), _wa_body, hashlib.sha256).hexdigest()

check("whatsapp sig: valid X-Hub signature verifies",
      verify_whatsapp_signature(_wa_body, _wa_sig) is True)
check("whatsapp sig: tampered body rejected",
      verify_whatsapp_signature(_wa_body + b" ", _wa_sig) is False)
check("whatsapp sig: missing sha256 prefix rejected",
      verify_whatsapp_signature(_wa_body, hmac.new(_WA_SECRET.encode(), _wa_body, hashlib.sha256).hexdigest()) is False)

# A user who opted in, then a signed inbound "STOP" auto-revokes their opt-in.
_wa_user = _mk_user("wa_stop@test", 0)
_conn = connect_db()
_conn.execute("UPDATE users SET phone_number = '+919876500000', whatsapp_opt_in = 1 WHERE id = ?", (_wa_user,))
_conn.commit()
_conn.close()

_wa_resp = _client.post("/api/whatsapp/webhook", content=_wa_body,
                        headers={"x-hub-signature-256": _wa_sig})
check("whatsapp webhook: verified STOP returns 200", _wa_resp.status_code == 200)
_conn = connect_db()
_optin = _conn.execute("SELECT whatsapp_opt_in FROM users WHERE id = ?", (_wa_user,)).fetchone()[0]
_conn.close()
check("whatsapp webhook: STOP revokes opt-in", _optin == 0)

# An unsigned/forged webhook is rejected (403) and never mutates state.
_wa_bad = _client.post("/api/whatsapp/webhook", content=_wa_body,
                       headers={"x-hub-signature-256": "sha256=deadbeef"})
check("whatsapp webhook: bad signature rejected (403)", _wa_bad.status_code == 403)


print("\n" + ("ALL RAZORPAY TESTS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
