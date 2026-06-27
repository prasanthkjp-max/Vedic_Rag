"""
Deterministic, no-server/no-browser unit tests for the high-risk pure logic.

Complements the Playwright UI suites (which need a live server + Chrome) and the
other pure-engine checks. Covers the things most likely to silently regress:
the dasa lookup boundaries, the muhurtham guards, the longest-match value
lookup (the Vaidhriti regression), the path-slug/tithi helpers, and the
credit debit→refund round-trip.

Runs standalone (`python3 test_unit.py`, exit 0/1) and in CI. Uses an isolated
temp DB so the credit tests never touch a real database.
"""
import os
import sys
import tempfile

# Isolate the DB BEFORE importing app/config (DB_PATH is captured at import).
_TMP = tempfile.mkdtemp(prefix="vedic_unit_")
os.environ["VEDIC_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ.setdefault("VEDIC_LOG_LEVEL", "ERROR")  # keep test output clean

import datetime
import secrets

failures = []


def check(name, cond):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


# ── prediction_engine.get_current_dasa ──────────────────────────────────────
from prediction_engine import get_current_dasa

DASA = [
    {"dasa_lord": "Ketu", "start_date": "2000-01-01", "end_date": "2007-01-01",
     "bhuktis": [
         {"bhukti_lord": "Ketu", "start_date": "2000-01-01", "end_date": "2001-01-01", "pratyantars": []},
         {"bhukti_lord": "Venus", "start_date": "2001-01-01", "end_date": "2003-01-01", "pratyantars": []},
     ]},
    {"dasa_lord": "Venus", "start_date": "2007-01-01", "end_date": "2027-01-01", "bhuktis": []},
]
check("dasa: ref inside window picks the maha", get_current_dasa(DASA, "2005-06-01")["mahadasa"] == "Ketu")
# Half-open [start, end): a date exactly on a boundary belongs to the NEW period.
check("dasa: boundary date picks the next maha", get_current_dasa(DASA, "2007-01-01")["mahadasa"] == "Venus")
check("dasa: ref inside first bhukti", get_current_dasa(DASA, "2000-06-01")["antardasa"] == "Ketu")
check("dasa: ref inside second bhukti", get_current_dasa(DASA, "2002-06-01")["antardasa"] == "Venus")
check("dasa: unparseable ref falls back, no crash", isinstance(get_current_dasa(DASA, "not-a-date"), dict))
check("dasa: ref before any period yields no maha", get_current_dasa(DASA, "1990-01-01")["mahadasa"] is None)

# ── muhurtham_engine guards & vishti edges ──────────────────────────────────
from muhurtham_engine import is_vishti_karana, calculate_muhurtham

check("vishti: index 0 is not Vishti", is_vishti_karana(0) is False)
check("vishti: index 7 is Vishti", is_vishti_karana(7) is True)
check("vishti: index 14 is Vishti", is_vishti_karana(14) is True)
check("vishti: index 56 is Vishti", is_vishti_karana(56) is True)
check("vishti: index 8 is not Vishti", is_vishti_karana(8) is False)

try:
    calculate_muhurtham("2026-03-05T06:00:00", 13.08, 80.27, "BOGUS_PARADIGM", "VIVAHA")
    _unknown_raised = False
except ValueError:
    _unknown_raised = True
check("muhurtham: unknown paradigm raises ValueError (no false-permit)", _unknown_raised)

try:
    calculate_muhurtham("2026-03-05T06:00:00", 13.08, 80.27, "TAMIL_SOLAR", "BOGUS_ACT")
    _unknown_act_raised = False
except ValueError:
    _unknown_act_raised = True
check("muhurtham: unknown activity raises ValueError", _unknown_act_raised)

# ── longest-match value lookup (the Vaidhriti regression) ────────────────────
from translations import YOGAM
from pdf_generator import _match_canon_idx

check("match: Vaidhriti -> 26 (not swallowed by 'dhriti')", _match_canon_idx(YOGAM["en"], "Vaidhriti") == 26)
check("match: Dhriti -> 7", _match_canon_idx(YOGAM["en"], "Dhriti") == 7)
check("match: Atiganda -> 5 (not 'ganda' at 9)", _match_canon_idx(YOGAM["en"], "Atiganda") == 5)
check("match: unknown -> -1", _match_canon_idx(YOGAM["en"], "Nonsense") == -1)

# ── app helpers + credit debit/refund round-trip ────────────────────────────
import app
from config import connect_db

check("liveness: /api/live reports alive (no deps)", app.liveness_probe()["status"] == "alive")
# /api/live must NOT be key-gated; only the corpus/admin endpoints are.
check("apikey: /api/live is not key-gated", app._is_key_protected("/api/live") is False)
check("apikey: /api/version is not key-gated", app._is_key_protected("/api/version") is False)
check("apikey: /api/search IS key-gated", app._is_key_protected("/api/search") is True)
check("apikey: /api/page-image/1/2 IS key-gated (prefix)", app._is_key_protected("/api/page-image/1/2") is True)
check("apikey: /api/books IS key-gated", app._is_key_protected("/api/books") is True)
check("apikey: /api/calculate-chart is not key-gated (session-gated instead)", app._is_key_protected("/api/calculate-chart") is False)
# /api/source must be public (AGPL §13) — neither key- nor corpus-gated.
check("source: /api/source is not key-gated", app._is_key_protected("/api/source") is False)

# Source archive (AGPL §13): builds a valid tarball with the source but NO secrets.
import tarfile as _tarfile
_src_path = app._source_archive_path()
check("source: archive path resolves", bool(_src_path) and os.path.exists(_src_path))
if _src_path and os.path.exists(_src_path):
    _tf = _tarfile.open(_src_path, "r:gz")
    _names = _tf.getnames()
    _tf.close()
    # strip any leading "./" git-archive prefixes for matching
    _norm = {n[2:] if n.startswith("./") else n for n in _names}
    check("source: archive contains app.py", "app.py" in _norm)
    check("source: archive contains LICENSE", "LICENSE" in _norm)
    _leaks = [n for n in _names if n.endswith(".env") or ".api_key" in n or n.endswith(".db")]
    check("source: archive leaks no secrets", _leaks == [])

check("safe_slug: neutralises traversal", ".." not in app._safe_slug("../../etc/foo"))
check("safe_slug: empty -> fallback", app._safe_slug("") == "chart")
check("tithi_num: exact parse", app._tithi_num("Sukla Paksha Prathama (Tithi 1)") == 1)
check("tithi_num: 11 not matched as 1", app._tithi_num("Krishna Paksha Ekadashi (Tithi 11)") == 11)
check("tithi_num: no marker -> 0", app._tithi_num("Pournami (Full Moon)") == 0)

# Seed a user + session in the isolated DB, then exercise the atomic debit/refund.
_conn = connect_db()
_cur = _conn.cursor()
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('unit@test', 100)")
_uid = _cur.lastrowid
_tok = secrets.token_hex(8)
_exp = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
_cur.execute("INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?, ?, ?)", (_tok, _uid, _exp))
_conn.commit()
_conn.close()


def _balance():
    c = connect_db()
    v = c.execute("SELECT credit_balance FROM users WHERE id = ?", (_uid,)).fetchone()[0]
    c.close()
    return v


_user = app.check_credits_or_raise(_tok, 50, "unit_test")
check("credits: debit leaves 50", _balance() == 50)
check("credits: charged recorded on user", _user.get("charged") == 50)
app.refund_user_credits(_user, "unit_test")
check("credits: refund restores 100", _balance() == 100)
app.refund_user_credits(_user, "unit_test")
check("credits: double refund is a no-op", _balance() == 100)

# Out-of-credits path: a 200-credit op on a 100-credit balance must 402, not overdraw.
from fastapi import HTTPException
try:
    app.check_credits_or_raise(_tok, 200, "unit_test")
    _raised_402 = False
except HTTPException as e:
    _raised_402 = (e.status_code == 402)
check("credits: insufficient balance raises 402", _raised_402)
check("credits: balance unchanged after a refused debit", _balance() == 100)


# ── billing_usage summary ────────────────────────────────────────────────────
# Fresh user with a known ledger: two debits + one purchase this month.
_conn = connect_db()
_cur = _conn.cursor()
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('usage@test', 475)")
_uid2 = _cur.lastrowid
_tok2 = secrets.token_hex(8)
_cur.execute("INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?, ?, ?)", (_tok2, _uid2, _exp))
_cur.execute("INSERT INTO credit_logs (user_id, amount, action_type) VALUES (?, -25, 'ai_predict')", (_uid2,))
_cur.execute("INSERT INTO credit_logs (user_id, amount, action_type) VALUES (?, -50, 'download_pdf')", (_uid2,))
_cur.execute("INSERT INTO credit_logs (user_id, amount, action_type) VALUES (?, 500, 'purchase')", (_uid2,))
_conn.commit()
_conn.close()


class _FakeReq:
    """Minimal Request stand-in: billing_usage only reads headers/cookies .get()."""
    def __init__(self, token):
        self.headers = {"x-session-token": token}
        self.cookies = {}


_usage = app.billing_usage(_FakeReq(_tok2))
check("usage: remaining balance reported", _usage["credits_remaining"] == 475)
check("usage: used-this-month sums debits only (25+50)", _usage["credits_used_this_month"] == 75)
check("usage: recent activity newest-first", _usage["recent_activity"][0]["action_type"] == "purchase")
check("usage: recent activity lists all rows", len(_usage["recent_activity"]) == 3)


# ── Phase 4: per-user rate limiting ──────────────────────────────────────────
# Injected clock + isolated bucket key so the test is deterministic.
app._RATE_BUCKETS.pop("rl_user", None)
for _i in range(3):
    app.rate_limit_or_raise("rl_user", limit=3, window=60, now=1000.0 + _i)
_rl_blocked = False
try:
    app.rate_limit_or_raise("rl_user", limit=3, window=60, now=1002.0)  # 4th in window
except HTTPException as e:
    _rl_blocked = (e.status_code == 429)
check("ratelimit: 4th call in window raises 429", _rl_blocked)
# After the window slides past the old timestamps, calls are allowed again.
app.rate_limit_or_raise("rl_user", limit=3, window=60, now=1100.0)
check("ratelimit: window expiry frees the bucket", len(app._RATE_BUCKETS["rl_user"]) == 1)
check("ratelimit: limit<=0 disables (no raise)", app.rate_limit_or_raise("rl_user", limit=0) is None)


# ── Phase 4: referral credits both sides ─────────────────────────────────────
_conn = connect_db()
_cur = _conn.cursor()
_cur.execute("INSERT INTO users (email, credit_balance, referral_code) VALUES ('ref_owner@test', 100, 'CODE1234')")
_referrer = _cur.lastrowid
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('ref_new@test', 25)")
_referee = _cur.lastrowid
_granted = app._apply_referral(_cur, _referee, "code1234")  # case-insensitive
_conn.commit()
def _bal(uid):
    return _cur.execute("SELECT credit_balance FROM users WHERE id=?", (uid,)).fetchone()[0]
check("referral: referee credited REFERRAL_BONUS_REFEREE", _bal(_referee) == 25 + app.REFERRAL_BONUS_REFEREE)
check("referral: referrer credited REFERRAL_BONUS_REFERRER", _bal(_referrer) == 100 + app.REFERRAL_BONUS_REFERRER)
check("referral: returns referee bonus", _granted == app.REFERRAL_BONUS_REFEREE)
check("referral: referred_by recorded", _cur.execute("SELECT referred_by FROM users WHERE id=?", (_referee,)).fetchone()[0] == _referrer)
# Unknown code and self-referral are no-ops.
check("referral: unknown code is a no-op", app._apply_referral(_cur, _referee, "NOPE9999") == 0)
check("referral: self-referral is a no-op", app._apply_referral(_cur, _referrer, "CODE1234") == 0)
_conn.commit()
_conn.close()


# ── Phase 4: subscriber soft-cap counter ─────────────────────────────────────
_conn = connect_db()
_cur = _conn.cursor()
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('cap@test', 0)")
_capuid = _cur.lastrowid
_conn.commit()
_conn.close()
_n1 = app.record_subscriber_usage(_capuid, now=datetime.datetime(2026, 1, 15))
_n2 = app.record_subscriber_usage(_capuid, now=datetime.datetime(2026, 1, 16))
check("softcap: counter increments within month", _n1 == 1 and _n2 == 2)
_n3 = app.record_subscriber_usage(_capuid, now=datetime.datetime(2026, 2, 1))
check("softcap: counter resets on new month", _n3 == 1)


# ── Recurring subscription: idempotent charge / activation ───────────────────
def _balance_of(uid):
    c = connect_db()
    v = c.execute("SELECT credit_balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    c.close()
    return v

def _sub_status(uid):
    c = connect_db()
    v = c.execute("SELECT status FROM subscriptions WHERE user_id=?", (uid,)).fetchone()[0]
    c.close()
    return v

def _grant_status():
    c = connect_db()
    v = c.execute("SELECT status FROM transactions WHERE payment_intent_id='order_IDOR'").fetchone()[0]
    c.close()
    return v

_conn = connect_db()
_cur = _conn.cursor()
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('subrenew@test', 0)")
_subuid = _cur.lastrowid
_cur.execute(
    "INSERT INTO subscriptions (user_id, status, tier, current_period_end, platform, platform_subscription_id) "
    "VALUES (?, 'created', 'astro', ?, 'razorpay', 'sub_RENEW1')",
    (_subuid, datetime.datetime.utcnow().isoformat()),
)
_conn.commit()
_conn.close()

_applied1, _ruid = app._apply_subscription_charge("sub_RENEW1", "pay_charge_1")
check("sub: first charge activates", _applied1 is True and _ruid == _subuid)
check("sub: status flipped to active", _sub_status(_subuid) == "active")
check("sub: refill credits granted", _balance_of(_subuid) == app.SUBSCRIPTION_REFILL_CREDITS)
# Same payment id again (webhook retry / callback race) must be a no-op.
_applied2, _ = app._apply_subscription_charge("sub_RENEW1", "pay_charge_1")
check("sub: duplicate payment id is idempotent (no double refill)",
      _applied2 is False and _balance_of(_subuid) == app.SUBSCRIPTION_REFILL_CREDITS)
# A genuine renewal (new payment id) tops up again.
_applied3, _ = app._apply_subscription_charge("sub_RENEW1", "pay_charge_2")
check("sub: new charge id renews (second refill)",
      _applied3 is True and _balance_of(_subuid) == 2 * app.SUBSCRIPTION_REFILL_CREDITS)
# Unknown subscription id is a no-op.
check("sub: unknown subscription id is a no-op",
      app._apply_subscription_charge("sub_NOPE", "pay_x")[0] is False)
# Lifecycle deactivation revokes the local pass.
app._deactivate_subscription("sub_RENEW1", "cancelled")
check("sub: deactivation sets terminal status", _sub_status(_subuid) == "cancelled")

# ── billing IDOR guard: verify paths bind the order/sub to the session user ──
from fastapi import HTTPException

_conn = connect_db()
_cur = _conn.cursor()
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('idor_owner@test', 10)")
_owner_id = _cur.lastrowid
_cur.execute("INSERT INTO users (email, credit_balance) VALUES ('idor_attacker@test', 10)")
_attacker_id = _cur.lastrowid
# A pending order that belongs to the owner.
_cur.execute(
    "INSERT INTO transactions (user_id, payment_intent_id, amount_cents, currency, status, payment_gateway, credits) "
    "VALUES (?, 'order_IDOR', 9900, 'INR', 'pending', 'razorpay', 500)",
    (_owner_id,),
)
# A pending subscription that belongs to the owner.
_cur.execute(
    "INSERT INTO subscriptions (user_id, status, tier, current_period_end, platform, platform_subscription_id) "
    "VALUES (?, 'created', 'astro', ?, 'razorpay', 'sub_IDOR')",
    (_owner_id, datetime.datetime.utcnow().isoformat()),
)
_conn.commit()
_conn.close()

# Attacker (expected_user_id) tries to claim the owner's order -> 403, no credit.
try:
    app._grant_credits_for_order("order_IDOR", "pay_x", "razorpay", expected_user_id=_attacker_id)
    _idor_blocked = False
except HTTPException as e:
    _idor_blocked = (e.status_code == 403)
check("idor: grant rejects a mismatched user (403)", _idor_blocked)
check("idor: attacker gained no credits", _balance_of(_attacker_id) == 10)
check("idor: owner's order still pending (un-granted)",
      _grant_status() == "pending" and _balance_of(_owner_id) == 10)

# The rightful owner can still be granted (regression: guard doesn't over-block).
_granted_ok, _credits = app._grant_credits_for_order(
    "order_IDOR", "pay_ok", "razorpay", expected_user_id=_owner_id)
check("idor: rightful owner is granted normally",
      _granted_ok is True and _balance_of(_owner_id) == 510)

# Same ownership guard on the subscription verify path.
try:
    app._apply_subscription_charge("sub_IDOR", "pay_sub_x", expected_user_id=_attacker_id)
    _idor_sub_blocked = False
except HTTPException as e:
    _idor_sub_blocked = (e.status_code == 403)
check("idor: subscription charge rejects a mismatched user (403)", _idor_sub_blocked)
check("idor: owner's subscription still un-charged",
      _sub_status(_owner_id) == "created")

print("\n" + ("ALL UNIT TESTS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
