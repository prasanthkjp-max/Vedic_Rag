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


print("\n" + ("ALL RAZORPAY TESTS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
