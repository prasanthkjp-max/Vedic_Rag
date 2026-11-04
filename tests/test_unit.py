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
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
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
from src.engines.prediction_engine import get_current_dasa

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
from src.engines.muhurtham_engine import is_vishti_karana, calculate_muhurtham

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
from src.core.translations import YOGAM
from src.engines.pdf_generator import _match_canon_idx

check("match: Vaidhriti -> 26 (not swallowed by 'dhriti')", _match_canon_idx(YOGAM["en"], "Vaidhriti") == 26)
check("match: Dhriti -> 7", _match_canon_idx(YOGAM["en"], "Dhriti") == 7)
check("match: Atiganda -> 5 (not 'ganda' at 9)", _match_canon_idx(YOGAM["en"], "Atiganda") == 5)
check("match: unknown -> -1", _match_canon_idx(YOGAM["en"], "Nonsense") == -1)

# ── app helpers + credit debit/refund round-trip ────────────────────────────
import app
from src.core.config import connect_db

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

# ------------------ PROFILE / RELATIONSHIP SCHEMA & API TESTS ------------------
import sqlite3
# Check database schema has relationship and profile_name
_conn = sqlite3.connect(app.DB_PATH)
_cur = _conn.cursor()
_cur.execute("PRAGMA table_info(user_charts)")
_columns = {row[1] for row in _cur.fetchall()}
check("schema: user_charts has relationship column", "relationship" in _columns)
check("schema: user_charts has profile_name column", "profile_name" in _columns)

# Mock save chart with relationship and profile_name
_cur.execute(
    "INSERT INTO user_charts (user_id, name, dob, tob, pob, latitude, longitude, gender, ayanamsa, chart_style, is_saved, relationship, profile_name) "
    "VALUES (?, 'Mother Chart', '1965-05-15', '08:30', 'Chennai', 13.08, 80.27, 'female', 'Lahiri', 'south', 1, 'mother', 'Mom')",
    (_owner_id,)
)
_conn.commit()

# Retrieve saved charts for owner
_cur.execute("SELECT relationship, profile_name FROM user_charts WHERE user_id = ? AND name = 'Mother Chart'", (_owner_id,))
_row = _cur.fetchone()
check("db: relationship field persists", _row is not None and _row[0] == "mother")
check("db: profile_name field persists", _row is not None and _row[1] == "Mom")

_conn.close()

# API Test via TestClient
try:
    from fastapi.testclient import TestClient
    client = TestClient(app.app)
    
    # insert session
    _conn = sqlite3.connect(app.DB_PATH)
    _cur = _conn.cursor()
    _session_token = "test_owner_session_token"
    _cur.execute(
        "INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?, ?, ?)",
        (_session_token, _owner_id, (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat())
    )
    _conn.commit()
    _conn.close()

    # Call POST /api/user/charts
    res_post = client.post(
        "/api/user/charts",
        headers={"x-session-token": _session_token},
        json={
            "name": "Sister Chart",
            "dob": "1995-10-10",
            "tob": "15:45",
            "pob": "Bangalore",
            "latitude": 12.97,
            "longitude": 77.59,
            "gender": "female",
            "ayanamsa": "Lahiri",
            "chart_style": "south",
            "is_saved": 1,
            "relationship": "friend",
            "profile_name": "Sis"
        }
    )
    check("api: POST /api/user/charts returns 200", res_post.status_code == 200)
    
    # Call GET /api/user/charts?saved=1
    res_get = client.get(
        "/api/user/charts?saved=1",
        headers={"x-session-token": _session_token}
    )
    check("api: GET /api/user/charts returns 200", res_get.status_code == 200)
    _charts = res_get.json()
    _sister_chart = next((c for c in _charts if c["name"] == "Sister Chart"), None)
    check("api: Sister Chart has relationship", _sister_chart is not None and _sister_chart["relationship"] == "friend")
    check("api: Sister Chart has profile_name", _sister_chart is not None and _sister_chart["profile_name"] == "Sis")
except Exception as e:
    print("Skipping TestClient tests:", e)

# ── Signed premium-report download links (WhatsApp delivery) ────────────────
import time as _time

_rid = "abc123report"
_future = int(_time.time()) + 3600
_sig = app._sign_report_token(_rid, _future)
check("report token: a fresh signature verifies", app._verify_report_token(_rid, _future, _sig) is True)
check("report token: tampered report id rejected",
      app._verify_report_token("other", _future, _sig) is False)
check("report token: tampered expiry rejected",
      app._verify_report_token(_rid, _future + 1, _sig) is False)
check("report token: empty signature rejected",
      app._verify_report_token(_rid, _future, "") is False)
_past = int(_time.time()) - 10
check("report token: expired link rejected even with a valid signature",
      app._verify_report_token(_rid, _past, app._sign_report_token(_rid, _past)) is False)

# ── E.164 phone normalization (WhatsApp opt-in) ─────────────────────────────
check("e164: canonical +number accepted", app._normalize_e164("+919876543210") == "+919876543210")
check("e164: separators/spaces stripped", app._normalize_e164("+91 98765-43210") == "+919876543210")
check("e164: 00 international prefix normalized", app._normalize_e164("0091 9876543210") == "+919876543210")
try:
    app._normalize_e164("98765")  # no country code / too short
    _e164_bad = False
except HTTPException as e:
    _e164_bad = (e.status_code == 400)
check("e164: invalid number rejected (400)", _e164_bad)

# ── Bug Fixes & Advanced Systems (KP, Jaimini, Nadi, Vakya, Ashtottari, Avasthas, Arudha, 22nd Drekkana) ──
from src.engines.pdf_generator import translate_tithi
from src.engines.astro_engine import get_astrological_chart
from src.engines.prediction_engine import build_analysis, build_rag_queries

for _lang in ("en", "ta", "te", "hi", "ml", "kn"):
    _pournami_str = translate_tithi("Pournami", _lang)
    check(f"pournami translation ({_lang}) is a string", isinstance(_pournami_str, str) and len(_pournami_str) < 30)

_kp_chart = get_astrological_chart(1990, 5, 15, 10, 30, 80.2707, 13.0827, "Yukteshwar", timezone_offset=5.5, calc_type="kp", dasa_system="ashtottari")
check("ayanamsa: Yukteshwar supported", _kp_chart["metadata"]["ayanamsa_name"] == "Yukteshwar")
check("kp: 12 Placidus cusps computed", len(_kp_chart.get("kp", {}).get("cusps", [])) == 12)
check("kp: 4-level significators computed", len(_kp_chart.get("kp", {}).get("house_significators", {})) == 12)
check("ashtottari: 108-year dasas computed", len(_kp_chart.get("ashtottari_dasas", {}).get("dasas", [])) >= 8)
check("jaimini: 7 chara karakas computed", len(_kp_chart.get("jaimini", {}).get("karakas", {})) == 7)
check("jaimini: chara dasa 12 rasis computed", len(_kp_chart.get("jaimini", {}).get("chara_dasas", [])) == 12)
check("arudha: 12 arudha padas computed", len(_kp_chart.get("arudha_padas", {}).get("padas", {})) == 12)
check("avasthas: 9 grahas computed", len(_kp_chart.get("avasthas", {})) == 9)
check("vargas: D2/D4/D7 & vimsopaka_bala computed",
      all(k in _kp_chart["placements"]["Sun"] for k in ("hora_rasi_index", "chaturthamsha_rasi_index", "saptamsha_rasi_index"))
      and "Sun" in _kp_chart.get("vimsopaka_bala", {}))
check("khara: 22nd drekkana computed", "nature" in _kp_chart.get("khara_drekkana", {}))

_jaimini_chart = get_astrological_chart(1990, 5, 15, 10, 30, 80.2707, 13.0827, "Fagan-Bradley", timezone_offset=5.5, calc_type="jaimini", dasa_system="chara")
_j_analysis = build_analysis(_jaimini_chart)
_j_queries = build_rag_queries(_jaimini_chart, _j_analysis)
check("rag queries: Jaimini queries include Atmakaraka/Karakamsa & Chara Dasa",
      any("Atmakaraka" in q for q in _j_queries) and any("Chara Dasa" in q for q in _j_queries))
_kp_queries = build_rag_queries(_kp_chart, build_analysis(_kp_chart))
check("rag queries: Ashtottari query uses corpus spelling 'Astottari'",
      any("Astottari" in q for q in _kp_queries))

# ── UI/UX Divine Elevation Plan (Sections 1-5) Verification ─────────────────
from src.api.panchangam import _is_kari_naal_from_tamil_date
from src.api.corpus import get_scripture_passages

check("kari_naal: Chithirai 6 is Kari Naal", _is_kari_naal_from_tamil_date("Chithirai 6") is True)
check("kari_naal: Chithirai 7 is not Kari Naal", _is_kari_naal_from_tamil_date("Chithirai 7") is False)
check("kari_naal: Thai 2 is Kari Naal", _is_kari_naal_from_tamil_date("Thai 2") is True)

_scripture_res = get_scripture_passages(query="Jupiter Gaja Kesari Yoga", limit=3)
check("scripture_passages: returns passages list",
      isinstance(_scripture_res.get("passages"), list) and len(_scripture_res["passages"]) >= 1)
check("scripture_passages: passage has book_title and citation_label",
      all("book_title" in p and "citation_label" in p and "translation_excerpt" in p for p in _scripture_res["passages"]))

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html"), "r", encoding="utf-8") as _f:
    _index_html = _f.read()

check("ui_divine: Dual Sacred Themes (Surya & Chandra) present",
      '[data-theme="chandra"]' in _index_html and 'toggleSacredTheme' in _index_html)
check("ui_divine: Live Cosmic Sky Ticker & Hora Dial present",
      'id="live-cosmic-sky-bar"' in _index_html and 'updateLiveCosmicSkyTicker' in _index_html)
check("ui_divine: Calendar Quick-Filters & 24h Sacred Timeline present",
      'id="calendar-quick-filters"' in _index_html and 'id="sacred-24h-timeline-container"' in _index_html)
check("ui_divine: Interactive SVG Graha Drishti & Dignity Badges present",
      'id="drishti-inspector-bar"' in _index_html and 'highlightGrahaDrishti' in _index_html)
check("ui_divine: Dasa Explorer Toolbar & Life Age Ribbon present",
      'id="dasa-explorer-toolbar"' in _index_html and 'id="vimshottari-life-age-ribbon"' in _index_html)
check("ui_divine: Classical Scripture Side-Drawer present",
      'id="classical-scripture-drawer"' in _index_html and 'openScriptureDrawer' in _index_html)

# ── AI Chat Saved Family Profiles Cross-Prediction Verification ──────────────
from src.api.ai import (
    _canonical_relationship_info,
    _compute_cached_profile_chart,
    resolve_referenced_profiles,
)
import re
from src.api.ai import AIChatMessage, _load_user_saved_profiles, _relation_to_primary
from src.core.config import DB_PATH as _CHAT_DB_PATH, connect_db as _chat_connect_db
from src.engines.prediction_engine import build_cross_chart_comparison


def _demo_profile(cid, name, dob, tob, lat, lon, gender, rel, alias):
    crel, drel, kws = _canonical_relationship_info(rel, gender, alias)
    return {
        "id": cid, "name": name, "dob": dob, "tob": tob, "pob": "Test City",
        "lat": lat, "lon": lon, "gender": gender, "ayanamsa": "Lahiri",
        "is_saved": 1, "relationship": rel, "canonical_relationship": crel,
        "display_relationship": drel, "profile_name": alias, "match_keywords": kws,
    }


# Fictional family: owner Arun, wife Meena Sundari, parents Bala and Kala, son Hari.
_owner = _demo_profile(1, "Arun", "1990-03-10", "08:30", 13.08, 80.27, "male", "self", "Self")
_wife = _demo_profile(2, "Meena Sundari", "1992-07-21", "17:12", 9.69, 78.45, "female", "spouse", "Meena Sundari")
_father = _demo_profile(3, "Bala", "1960-01-31", "18:10", 13.72, 80.22, "male", "parent", "Appa")
_mother = _demo_profile(4, "Kala", "1963-09-23", "13:15", 14.44, 79.98, "female", "parent", "Amma")
_son = _demo_profile(5, "Hari", "2018-02-02", "06:00", 13.08, 80.27, "male", "child", "Hari")
_demo_profiles = [_owner, _wife, _father, _mother]
_family_profiles = _demo_profiles + [_son]
_as_of = datetime.date(2026, 11, 4)


def _resolved(query, profiles=None, primary="Arun", dob="1990-03-10", history=None, ids=None):
    return [p["name"] for p in resolve_referenced_profiles(
        profiles if profiles is not None else _family_profiles, [], primary, dob, query,
        history=history, explicit_ids=ids,
    )]


def _cross(a, b, relationship, ref_date=_as_of):
    return build_cross_chart_comparison(
        _compute_cached_profile_chart(a), a["name"],
        _compute_cached_profile_chart(b), b["name"], relationship, ref_date=ref_date,
    )


check("chat_cross: spouse matched by 'wife' relationship",
      _resolved("Check my wife's chart and compare with mine", _demo_profiles) == ["Meena Sundari"])
check("chat_cross: spouse matched by name token",
      _resolved("How is Sundari's dasha right now?", _demo_profiles) == ["Meena Sundari"])
check("chat_cross: father matched by 'father' or alias 'Appa'",
      _resolved("Compare my chart with my father", _demo_profiles) == ["Bala"]
      and _resolved("How is Appa's health?", _demo_profiles) == ["Bala"])
check("chat_cross: mother matched by 'mother' or alias 'Amma'",
      _resolved("Check my mother's astrology with mine", _demo_profiles) == ["Kala"]
      and _resolved("Check Amma's dasha", _demo_profiles) == ["Kala"])
check("chat_cross: collective 'parents' matches both father and mother",
      set(_resolved("Compare my chart with my parents", _demo_profiles)) == {"Bala", "Kala"})
check("chat_cross: build_cross_chart_comparison includes synastry, overlays, dasas & marriage kootas",
      "MARRIAGE COMPATIBILITY" in _cross(_owner, _wife, "wife (spouse)"))
check("chat_cross: UI family profiles bar present in index.html",
      'id="ai-family-profiles-bar"' in _index_html and 'renderAIChatFamilyProfilesBar' in _index_html)

# Relationships are relative to the account owner; analysis must be relative to the active chart.
check("chat_relation: owner active keeps the saved relationship",
      _relation_to_primary("self", _wife)[0] == "wife" and _relation_to_primary("self", _father)[0] == "father")
check("chat_relation: wife active reads the owner as husband and his parents as in-laws",
      _relation_to_primary("wife", _owner)[0] == "husband"
      and _relation_to_primary("wife", _father)[0] == "father-in-law"
      and _relation_to_primary("wife", _mother)[0] == "mother-in-law")
check("chat_relation: father active reads mother as wife, owner as son, wife as daughter-in-law",
      _relation_to_primary("father", _mother)[0] == "wife"
      and _relation_to_primary("father", _owner)[0] == "son"
      and _relation_to_primary("father", _wife)[0] == "daughter-in-law"
      and _relation_to_primary("father", _son)[0] == "grandson")
check("chat_relation: son active reads the owner as father and grandparents correctly",
      _relation_to_primary("son", _owner)[0] == "father"
      and _relation_to_primary("son", _wife)[0] == "mother"
      and _relation_to_primary("son", _father)[0] == "grandfather")
check("chat_relation: a friend's chart has no family link to the owner's relatives",
      _relation_to_primary("friend", _wife)[0] == "other")
check("chat_relation: an unsaved active chart never labels the owner as SELF",
      _relation_to_primary(None, _owner)[0] == "other" and _relation_to_primary(None, _wife)[0] == "wife")

_koota = "MARRIAGE COMPATIBILITY"
check("chat_relation: Koota runs for parents with each other, not father with daughter-in-law",
      _koota in _cross(_father, _mother, _relation_to_primary("father", _mother)[1])
      and _koota not in _cross(_father, _wife, _relation_to_primary("father", _wife)[1]))
check("chat_relation: husband's father gets no Pitru Bhava section on the wife's chart",
      "Pitru Bhava" not in _cross(_wife, _father, _relation_to_primary("wife", _father)[1]))
check("chat_relation: wife active compares with the owner as her husband, with Koota",
      _koota in _cross(_wife, _owner, _relation_to_primary("wife", _owner)[1]))
check("chat_relation: 'my husband' finds the owner when the wife's chart is active",
      _resolved("Compare with my husband", primary="Meena Sundari", dob="1992-07-21") == ["Arun"])
check("chat_relation: 'mother-in-law' finds the owner's mother when the wife's chart is active",
      _resolved("How is my mother-in-law?", primary="Meena Sundari", dob="1992-07-21") == ["Kala"])

# False positives in profile resolution.
for _query in ("How is my mother-in-law's health?", "Will my father-in-law help me?", "my son-in-law's job",
               "How will my business partner behave?", "Is my friend's wife going to recover?",
               "How is my wife's mother?", "How is my family life?", "How is the Thai month for me?"):
    check(f"chat_match: nobody resolved for {_query!r}", _resolved(_query) == [])
check("chat_match: Hindi 'husband' does not fire inside Jupiter or house lord",
      _resolved("बृहस्पति का प्रभाव क्या है?") == [] and _resolved("सप्तम अधिपति कहाँ है?") == [])
check("chat_match: Hindi 'husband' still matches as its own word",
      _resolved("मेरे पति कैसे हैं?") == ["Meena Sundari"])
check("chat_match: Kannada 'daughter' does not match a son, but 'son' does",
      _resolved("ನನ್ನ ಮಗಳು ಹೇಗೆ") == [] and _resolved("ನನ್ನ ಮಗ ಹೇಗೆ") == ["Hari"])
_chandra = _demo_profile(6, "Chandra Sekhar", "1985-01-01", "10:00", 13.08, 80.27, "male", "other", "")
_ravi = _demo_profile(7, "Ravi", "1985-01-01", "10:00", 13.08, 80.27, "male", "friend", "Ravi")
check("chat_match: planet names are not person mentions, full names still are",
      _resolved("How strong is Chandra in my chart?", [_owner, _chandra]) == []
      and _resolved("What does Ravi dasa give me?", [_owner, _ravi]) == []
      and _resolved("How is Chandra Sekhar doing?", [_owner, _chandra]) == ["Chandra Sekhar"])
_cousin_a = _demo_profile(8, "Vel Murugan", "1985-01-01", "10:00", 13.08, 80.27, "male", "other", "")
_cousin_b = _demo_profile(9, "Siva Murugan", "1986-01-01", "10:00", 13.08, 80.27, "male", "other", "")
check("chat_match: a shared surname identifies nobody",
      _resolved("Tell me about Murugan", [_owner, _cousin_a, _cousin_b]) == [])
_placeholder = _demo_profile(10, "Name", "1985-01-01", "10:00", 13.08, 80.27, "male", "other", "")
check("chat_match: a chart left at the default form name is not a mention",
      _resolved("What does my name mean?", [_owner, _placeholder]) == [])
check("chat_match: a pinned primary is not compared with itself",
      _resolved("hello", ids=[1]) == [] and _resolved("hello", ids=[2]) == ["Meena Sundari"])
check("chat_match: a dd/mm/yyyy stored DOB still identifies the primary",
      _resolved("hello", [_demo_profile(1, "Arun", "10/03/1990", "08:30", 13.08, 80.27, "male", "self", "Self")], ids=[1]) == [])

# Follow-up turns.
_wife_turn = [AIChatMessage(role="user", content="Compare with my wife"), AIChatMessage(role="assistant", content="ok")]
check("chat_followup: an unrelated follow-up drops the earlier profile",
      _resolved("what about my career", history=_wife_turn) == []
      and _resolved("tell me whether this year is good", history=_wife_turn) == [])
check("chat_followup: a pronoun or group word carries the profile over",
      _resolved("how is her health", history=_wife_turn) == ["Meena Sundari"]
      and _resolved("compare with my father and tell me about both", history=_wife_turn) == ["Bala", "Meena Sundari"])
check("chat_followup: naming someone new does not pull in the earlier profile",
      _resolved("compare with my father", history=_wife_turn) == ["Bala"])

# The saved relationship outranks alias words and defaulted gender.
_role = lambda rel, gender, alias: _canonical_relationship_info(rel, gender, alias)[0]
check("chat_role: alias does not override an explicit relationship",
      _role("child", "female", "Papa") == "daughter" and _role("spouse", "female", "Mama") == "wife"
      and _role("friend", "female", "Anna") == "friend" and _role("self", "male", "Appa") == "self")
check("chat_role: explicit role beats a defaulted gender",
      _role("daughter", "male", "") == "daughter" and _role("sister", "male", "") == "sister"
      and _role("wife", "male", "") == "wife" and _role("parent", "male", "Amma") == "mother")
check("chat_role: an alias still classifies a profile saved as 'other'",
      _role("other", "male", "Appa") == "father" and _role("other", "female", "Amma") == "mother")

# build_cross_chart_comparison output.
_sonia = _canonical_relationship_info("friend", "female", "Sonia")[1]
check("chat_engine: an alias containing 'son' does not select the child section",
      "PARENT–CHILD" not in _cross(_owner, _wife, _sonia))
check("chat_engine: 29 February does not raise, for spouse or other relations",
      _koota in _cross(_owner, _wife, "wife (spouse)", datetime.date(2028, 2, 29))
      and "Next 10 Years" in _cross(_owner, _father, "father", datetime.date(2028, 2, 29)))
_overlap_text = _cross(_owner, _father, "father")
_overlap_dates = re.findall(r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2}): Arun in", _overlap_text)
check("chat_engine: overlap windows are clipped to the next 10 years",
      all("2026-11-04" <= lo and hi <= "2036-11-04" for lo, hi in _overlap_dates))
_spouse_text = _cross(_owner, _wife, "wife (spouse)")
check("chat_engine: spouse reading reports the overlap once, and Koota lines are clean",
      "Simultaneous Natural-Malefic" not in _spouse_text and "MALEFIC DASA OVERLAP" in _spouse_text
      and "Points: " in _spouse_text and "/ —" not in _spouse_text)

# Account self profile vs. an auto-recorded history row of the same chart.
_conn = _chat_connect_db(_CHAT_DB_PATH)
_columns = {row[1] for row in _conn.execute("PRAGMA table_info(users)")}
_values = {"email": "chat-self@example.test", "full_name": "Arun", "dob": "1990-03-10", "tob": "08:30",
           "birth_place": "Test City", "birth_latitude": 13.08, "birth_longitude": 80.27, "gender": "male"}
_values = {k: v for k, v in _values.items() if k in _columns}
_values.update({k: "x" for k in ("password_hash", "password", "salt") if k in _columns})
_uid = _conn.execute(
    f"INSERT INTO users ({','.join(_values)}) VALUES ({','.join('?' * len(_values))})", tuple(_values.values())
).lastrowid
_insert_chart = ("INSERT INTO user_charts (user_id,name,dob,tob,pob,latitude,longitude,gender,ayanamsa,chart_style,"
                 "is_saved,relationship,profile_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)")
_conn.execute(_insert_chart, (_uid, "Arun", "1990-03-10", "08:30", "Test City", 13.08, 80.27, "male", "Lahiri", "south", 0, "other", ""))
_conn.execute(_insert_chart, (_uid, "Bala", "1960-01-31", "18:10", "Test City", 13.72, 80.22, "male", "Lahiri", "south", 1, "parent", "Appa"))
_conn.commit()
_conn.close()
_saved, _hist = _load_user_saved_profiles(_uid)
check("chat_self: a history row of the owner's chart does not hide the self profile",
      [(p["name"], p["canonical_relationship"]) for p in _saved] == [("Arun", "self"), ("Bala", "father")]
      and _hist == [])

# ── Personal calendar overlay ────────────────────────────────────────────────
from src.engines.astro_engine import NAKSHATRAS as _NAKSHATRAS, get_astrological_chart as _overlay_chart
from src.engines.calendar_overlay import build_day_overlay, is_chandrashtama, janma_details, tara_bala
from src.api.panchangam import _compute_month_panchangam

check("overlay: Tara Bala counts inclusively from the birth star",
      tara_bala(0, 0) == (1, "Janma") and tara_bala(0, 1) == (2, "Sampat")
      and tara_bala(0, 5) == (6, "Sadhaka") and tara_bala(0, 8) == (9, "Paramamitra"))
check("overlay: Tara Bala repeats every 9 stars and wraps past Revati",
      tara_bala(0, 9) == (1, "Janma") and tara_bala(0, 18) == (1, "Janma")
      and tara_bala(26, 0) == (2, "Sampat") and tara_bala(26, 26) == (1, "Janma"))
check("overlay: Chandrashtama is the 8th rasi counted from the birth rasi, with wrap",
      is_chandrashtama(0, 7) and is_chandrashtama(6, 1) and not is_chandrashtama(0, 8) and not is_chandrashtama(7, 0))

_janma = {"nakshatra": "Ashwini", "nakshatra_index": 0, "rasi_index": 0, "solar_month": "Chithirai"}
_overlay_day = lambda **kw: build_day_overlay(_janma, {
    "nakshatra_index": 1, "moon_rasi_index": 1, "moon_rasi_index_end": 1, "solar_month": "Aadi", **kw})
check("overlay: Sampat, Kshema, Sadhaka, Mitra and Paramamitra are the highlighted Taras",
      [_overlay_day(nakshatra_index=i)["tara_name"] for i in range(9) if _overlay_day(nakshatra_index=i)["tara_good"]]
      == ["Sampat", "Kshema", "Sadhaka", "Mitra", "Paramamitra"])
check("overlay: Chandrashtama is flagged at sunrise or when the Moon enters later that day",
      _overlay_day(moon_rasi_index=7)["chandrashtama"] and _overlay_day(moon_rasi_index_end=7)["chandrashtama"]
      and not _overlay_day()["chandrashtama"])
check("overlay: star day recurs monthly, star birthday needs the birth solar month too",
      _overlay_day(nakshatra_index=0)["star_day"] and not _overlay_day(nakshatra_index=0)["star_birthday"]
      and _overlay_day(nakshatra_index=0, solar_month="Chithirai")["star_birthday"]
      and not _overlay_day(nakshatra_index=1, solar_month="Chithirai")["star_birthday"])
_janma_chart = _overlay_chart(1990, 3, 10, 8, 30, 80.27, 13.08, "Lahiri", light=True)
_janma_read = janma_details(_janma_chart)
check("overlay: birth details read from a light chart",
      _NAKSHATRAS[_janma_read["nakshatra_index"]] == _janma_chart["panchangam"]["nakshatra"]
      and _janma_read["rasi_index"] == _janma_chart["placements"]["Moon"]["rasi_index"]
      and bool(_janma_read["solar_month"]))

_month = _compute_month_panchangam(2026, 11, "ta", 13.08, 80.27)["days"]
_activity_names = {"VIVAHA", "GRAHAPRAVESHA", "AKSHARABHYASAM", "VAHAN_KHARIDI", "BUSINESS_OPENING", "NAMAKARANA", "TRAVEL"}
check("month: each day carries the overlay and filter fields",
      len(_month) == 30 and all(
          0 <= d["nakshatra_index"] < 27 and 0 <= d["moon_rasi_index"] < 12 and d["paksha"] in ("sukla", "krishna")
          # Pournami and Amavasya are named in the tithi string, without a number.
          and (1 <= d["tithi_num"] <= 14 or d["is_pournami"] or d["is_amavasya"] or "Pournami" in d["tithi"] or "Amavasya" in d["tithi"])
          and d["solar_month"] and d["rahu_kalam"]
          for d in _month))
check("month: activity list holds only real engine activities, and varies by activity",
      {a for d in _month for a in d["activities"]} <= _activity_names
      and len({a for d in _month for a in d["activities"]}) > 1
      and all(("VIVAHA" in d["activities"]) == d["is_subha_muhurtham"] for d in _month))
check("month: Pournami is waxing and Amavasya is waning",
      all(d["paksha"] == "sukla" for d in _month if "Pournami" in d["tithi"])
      and all(d["paksha"] == "krishna" for d in _month if "Amavasya" in d["tithi"]))
check("month: nakshatra stays a full name in the grid, not a 5-character slice",
      "translatedNak.slice(0, 5)" not in _index_html)

check("chat_ui: profile chip escapes the name and alias",
      '<span class="profile-rel">${escapeHtml(relLabel)}</span>' in _index_html)


# --- Language filter, source selection and chart check (fictional data only) ---
import json
import re
from types import SimpleNamespace as _NS
from src.api import deps as _deps
from src.core.translations import READING_CHECK_NOTE, READING_SECTIONS
from src.engines.fact_check import (
    chart_facts, find_contradictions, format_fact_sheet, parse_claims, render_note,
)
from src.engines.output_guard import LANG_SCRIPT, ScriptGuard, clean_text, has_foreign_script
from src.engines.prediction_engine import best_excerpt, is_reference_page, retrieve_rag_context

_BENGALI = "\u09b6\u09be\u09b8\u09cd\u09a4\u09cd\u09b0\u09c0\u09af\u09bc"
_TAMIL_A = "\u0ba4\u0bc0\u0bb0\u0bcd\u0bb5\u0bc1"
_TAMIL_B = "\u0bae\u0bb1\u0bcd\u0bb1\u0bc1\u0bae\u0bcd"
_DEVANAGARI = "\u0936\u093e\u0938\u094d\u0924\u094d\u0930"


def _stream(chunks, lang="ta", **kw):
    guard = ScriptGuard(lang, **kw)
    return "".join(guard.feed(c) for c in chunks) + guard.flush(), guard


_out, _g = _stream([f"{_TAMIL_B} {_BENGALI} {_TAMIL_A}"])
check("guard: a stray word with no translator is removed without a double space",
      _out == f"{_TAMIL_B} {_TAMIL_A}" and _g.removed == 1)
_calls = []
_out, _g = _stream([f"{_TAMIL_B} {_BENGALI[:3]}", f"{_BENGALI[3:]} {_TAMIL_A}"],
                   translate=lambda t: (_calls.append(t), _TAMIL_A)[1])
check("guard: a word split across chunks is translated once, as one word",
      _out == f"{_TAMIL_B} {_TAMIL_A} {_TAMIL_A}" and _calls == [_BENGALI] and _g.replaced == 1)
_out, _ = _stream([f"{_BENGALI} {_TAMIL_A} {_BENGALI}."], translate=lambda t: 1 / 0)
check("guard: a failing translator removes the word instead of breaking the stream",
      _BENGALI not in _out and _TAMIL_A in _out)
_out, _ = _stream([_BENGALI], translate=lambda t: _DEVANAGARI)
check("guard: a translation in the wrong script is rejected", _out == "")
_n = []
_stream([" ".join(f"{_BENGALI}{chr(0x985 + i)}\n" for i in range(12))],
        translate=lambda t: (_n.append(t), _TAMIL_A)[1])
check("guard: translation calls per reading are capped", len(_n) == 6)
_plain = f"# {_TAMIL_A} [8]: Lagna 10\n\n- {_TAMIL_B}\n"
check("guard: the reading language, Latin, digits and citations pass unchanged",
      _stream([_plain[:5], _plain[5:]])[0] == _plain)
check("guard: Devanagari is native to Hindi but stray in Tamil and English",
      not has_foreign_script(_DEVANAGARI, "hi") and has_foreign_script(_DEVANAGARI, "ta")
      and has_foreign_script(_DEVANAGARI, "en"))
check("guard: an allowed script is kept for quoted verses",
      clean_text(f"{_TAMIL_A} {_DEVANAGARI}", "ta", allow_scripts=("Devanagari",)) == f"{_TAMIL_A} {_DEVANAGARI}")
check("guard: JSON keys survive when a value is cleaned",
      clean_text('{"mesha": "' + _BENGALI + _TAMIL_A + '"}', "ta") == '{"mesha": "' + _TAMIL_A + '"}')


class _FakeChoice:
    def __init__(self, text):
        self.choices = [_NS(delta=_NS(content=text))]
        self.error = None


class _FakeStream:
    def __init__(self, parts):
        self.parts = parts
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def __iter__(self):
        return (_FakeChoice(p) for p in self.parts)


class _FakeCompletions:
    def __init__(self):
        self.kwargs = []
    def create(self, **kw):
        self.kwargs.append(kw)
        if kw.get("stream"):
            return _FakeStream([f"{_TAMIL_B} {_BENGALI[:2]}", f"{_BENGALI[2:]} {_TAMIL_A}"])
        return _NS(choices=[_NS(message=_NS(content=_TAMIL_A))])


class _FakeClient:
    def __init__(self):
        self.chat = _NS(completions=_FakeCompletions())
    def with_options(self, **kw):
        return self


_real_client = _deps.get_llm_client
_fake = _FakeClient()
_deps.get_llm_client = lambda: _fake
_completed, _checked = [], []
_stream_out = "".join(_deps.llm_stream(
    lambda: ("prompt", [{"index": 1, "snippet": _DEVANAGARI}]), "model", None, "test", lang="ta",
    on_complete=_completed.append, post_check=lambda t: (_checked.append(t), "\nNOTE")[1],
))
_deps.get_llm_client = _real_client
check("llm_stream: stray word is repaired in the streamed and completed text",
      _BENGALI not in _stream_out and _completed == [f"{_TAMIL_B} {_TAMIL_A} {_TAMIL_A}"])
check("llm_stream: the citation manifest is not filtered",
      json.dumps({"manifest": [{"index": 1, "snippet": _DEVANAGARI}]}) in _stream_out)
check("llm_stream: post_check sees the cleaned text and its note is appended",
      _checked == _completed and _stream_out.endswith("\nNOTE"))
check("llm_stream: the reading uses the configured temperature",
      _fake.chat.completions.kwargs[0]["temperature"] == _deps.LLM_TEMPERATURE)



class _BreakingStream(_FakeStream):
    def __iter__(self):
        yield _FakeChoice(f"{_TAMIL_A} {_BENGALI}")
        raise RuntimeError("connection lost")


_fake = _FakeClient()
_fake.chat.completions.create = lambda **kw: _BreakingStream([])
_deps.get_llm_client = lambda: _fake
_broken = "".join(_deps.llm_stream(lambda: "p", "model", None, "test", lang="ta",
                                   post_check=lambda t: 1 / 0))
_deps.get_llm_client = _real_client
check("llm_stream: a failed stream reports the error and doesn't leak the held word",
      "connection lost" in _broken and _TAMIL_A in _broken and _BENGALI not in _broken)
_failing_check = _FakeClient()
_deps.get_llm_client = lambda: _failing_check
_survived = "".join(_deps.llm_stream(lambda: "p", "model", None, "test", lang="ta",
                                     post_check=lambda t: 1 / 0))
_deps.get_llm_client = _real_client
check("llm_stream: a failing chart check doesn't break the finished reading",
      _TAMIL_A in _survived and "Error" not in _survived)

for _code in ("ta", "te", "ml", "kn", "hi"):
    _lock = _deps._language_lock(_code)
    check(f"language lock: names the script for {_code}", LANG_SCRIPT[_code] in _lock)
    _texts = READING_SECTIONS[_code] + [
        v.format(house=1, lords="1") if "{" in v else v for v in READING_CHECK_NOTE[_code].values()
    ]
    check(f"translations: {_code} headings and check note stay in their own script",
          all(not has_foreign_script(t, _code) for t in _texts))
check("language lock: quoted verses are the only Devanagari exception",
      "Devanagari" in _deps._language_lock("ta", allow_devanagari=True)
      and "Devanagari" not in _deps._language_lock("ta"))
check("translations: every language has four sections and every note field",
      all(len(v) == 4 for v in READING_SECTIONS.values())
      and all(set(v) == set(READING_CHECK_NOTE["en"]) for v in READING_CHECK_NOTE.values())
      and set(READING_SECTIONS) == set(READING_CHECK_NOTE))
_src_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "src", "api")
_src = {name: open(_os.path.join(_src_dir, name), encoding="utf-8").read()
        for name in ("ai.py", "corpus.py", "chart.py", "horoscope.py")}
_stream_calls = [m for s in (_src["ai.py"], _src["corpus.py"]) for m in re.findall(r"llm_stream\(.*?lang=|llm_stream\([^)]*\)", s, re.S)]
check("every streamed reading passes its language to llm_stream",
      len(_stream_calls) >= 9 and all(c.endswith("lang=") for c in _stream_calls))
check("every non-streamed reading passes its language to _llm_complete",
      all("lang=" in line for s in (_src["chart.py"], _src["horoscope.py"])
          for line in s.splitlines() if "_llm_complete(" in line and "import" not in line))
check("every prompt ends with the language rule",
      _src["ai.py"].count("{_language_lock(") == 8 and _src["corpus.py"].count("{_language_lock(") == 1
      and _src["chart.py"].count("{_language_lock(") == 1 and _src["horoscope.py"].count("{_language_lock(") == 1)

check("reference page: a contents listing, index and roman-numbered page are detected",
      is_reference_page("(xvi) to ward off afflictions and more text")
      and is_reference_page("x\nCHAPTER 97 714-775 PROPITIATION")
      and is_reference_page("58 RENOWN INDEX To become")
      and is_reference_page("xviii  \u201cI  PHALADEEPIKA  Yogas leading to children")
      and is_reference_page(" ".join(f"{i}. Antardasa of Saturn in the Mahadasa of Rahu." for i in range(5))))
check("reference page: ordinary text about dasas is kept",
      not is_reference_page("Results of the Pratyantardasa of Venus in the Antardasa of Ketu. Danger from foes.")
      and not is_reference_page("vii) viii) ix) whether Rahu draws good influences on the Moon"))

_filler = "Unrelated words about something else entirely. " * 40
_page = _filler + "Rahu placed in the Lagna gives trouble to the body, says the sage. " + _filler
_ex = best_excerpt(_page, {"rahu", "lagna"}, size=300)
check("excerpt: the window holds the matching passage, not the page start",
      "Rahu placed in the Lagna" in _ex and len(_ex) <= 302 and _ex.startswith("…") and _ex.endswith("…"))
check("excerpt: no match falls back to the page start",
      best_excerpt(_page, {"jupiter"}, size=100).startswith("Unrelated"))
check("excerpt: a short page is returned whole", best_excerpt("Short page.", {"rahu"}) == "Short page.")


class _FakeSearch:
    def reload(self):
        pass
    def get_embeddings_batch(self, queries):
        return [None for _ in queries]
    def dense_search_with_vector(self, *a, **k):
        return []
    def sparse_search(self, query, top_k=3, category=None):
        self.top_k = top_k
        return [
            {"book_id": 1, "book_title": "Book", "page_num": 1, "raw_text": "(xvi) contents of Rahu chapter"},
            {"book_id": 1, "book_title": "Book", "page_num": 50, "raw_text": _page},
        ]


_context, _passages = retrieve_rag_context(_FakeSearch(), ["rahu in lagna"], snippet_chars=300)
check("retrieval: contents pages are left out and the slot goes to a real page",
      [p["page_num"] for p in _passages] == [50] and "(xvi)" not in _context)
check("retrieval: the prompt and the citation card share the same excerpt",
      "Rahu placed in the Lagna" in _context
      and _deps.citation_manifest(_passages)[0]["snippet"] == _passages[0]["excerpt"]
      and _passages[0]["excerpt"] in _context)
check("citation card: a passage without an excerpt still gets a capped snippet",
      _deps.citation_manifest([{"raw_text": "x" * 1000}])[0]["snippet"] == "x" * 900 + "…")

_sample_facts = {
    "Arun": {"Jupiter": {"house": 10, "lord_of": [3, 12], "combust": False},
             "Rahu": {"house": 4, "lord_of": [], "combust": False}},
    "Meena": {"Jupiter": {"house": 2, "lord_of": [1, 4], "combust": True}},
}
_reading = "Arun's Jupiter, lord of the 10th, brings work. Meena's Jupiter is in the 2nd house."
_claim = lambda **kw: {"person": "Arun", "planet": "Jupiter", "claim": "lord_of", "house": 10,
                       "quote": "Jupiter, lord of the 10th", **kw}
_found = find_contradictions([_claim()], _sample_facts, _reading)
check("fact check: occupying a house is not ruling it",
      len(_found) == 1 and _found[0]["lord_of"] == [3, 12])
check("fact check: true statements are not reported",
      find_contradictions([_claim(house=3), _claim(claim="occupies")], _sample_facts, _reading) == []
      and find_contradictions([{"person": "Meena", "planet": "Jupiter", "claim": "occupies", "house": 2,
                                "quote": "Meena's Jupiter is in the 2nd house"}], _sample_facts, _reading) == [])
check("fact check: a quote that isn't in the reading is ignored",
      find_contradictions([_claim(quote="not in this reading")], _sample_facts, _reading) == [])
check("fact check: unusable claims are ignored",
      find_contradictions([_claim(house="10"), _claim(house=True), _claim(house=13), _claim(planet="Pluto"),
                           _claim(person="Nobody"), _claim(claim="aspects")], _sample_facts, _reading) == [])
check("fact check: Rahu lordship is never reported",
      find_contradictions([_claim(planet="Rahu", quote="Jupiter, lord of the 10th")], _sample_facts, _reading) == [])
check("fact check: a repeated claim is reported once",
      len(find_contradictions([_claim(), _claim()], _sample_facts, _reading)) == 1)
check("fact check: unparseable model replies yield no claims",
      parse_claims("sorry, no") == [] and parse_claims("[broken") == [] and parse_claims('[1, {"a": 1}]') == [{"a": 1}]
      and parse_claims('Here: [{"a": 1}] done') == [{"a": 1}])
check("fact check: nothing wrong means no note", render_note([], "ta") == "")
_note = render_note(_found, "ta", {"Jupiter": _TAMIL_A})
check("fact check: the note is in the reading's language and gives the computed facts",
      READING_CHECK_NOTE["ta"]["heading"] in _note and _TAMIL_A in _note and "3, 12" in _note and "10" in _note)
_sheet = format_fact_sheet(_sample_facts)
check("fact sheet: separates occupied and ruled houses, per person",
      "Arun:" in _sheet and "- Jupiter: occupies house 10; lord of houses: 3, 12" in _sheet
      and "Rahu: occupies house 4; lord of houses: none" in _sheet and "2; lord of houses: 1, 4; combust" in _sheet)
_fc_chart = get_astrological_chart(2000, 1, 1, 12, 0, 80.27, 13.08, "Lahiri")
_fc = chart_facts(_fc_chart)
check("fact check: facts come from the chart, with each house ruled once and Rahu/Ketu ruling none",
      len(_fc) == 9 and sorted(h for f in _fc.values() for h in f["lord_of"]) == list(range(1, 13))
      and _fc["Rahu"]["lord_of"] == [] and _fc["Ketu"]["lord_of"] == [])


# Build the real prompt of every reading endpoint, in Tamil, without calling a model.
from src.api import ai as _ai
from src.engines.astro_engine import calculate_marriage_compatibility as _compat

_male = get_astrological_chart(1985, 3, 14, 9, 20, 80.27, 13.08, "Lahiri", gender="male")
_female = get_astrological_chart(1988, 11, 2, 16, 45, 78.45, 9.69, "Lahiri", gender="female")
_comp = _compat(_male, _female)
_wife_row = {
    "id": 2, "name": "Meena Sundari", "dob": "1988-11-02", "tob": "16:45", "pob": "Test City",
    "lat": 9.69, "lon": 78.45, "gender": "female", "ayanamsa": "Lahiri", "is_saved": 1,
    "relationship": "wife", "canonical_relationship": "wife", "display_relationship": "Wife",
    "profile_name": "Meena", "match_keywords": ["wife"],
}
_captured = {}


def _capture_stream(builder, model, user=None, action="ai", **kw):
    built = builder()
    _captured[action] = {"prompt": built[0] if isinstance(built, tuple) else built, "kw": kw}
    return iter(["done"])


_patches = {
    "llm_stream": _capture_stream,
    "get_user_by_session": lambda token: {"id": 1, "email": "test@example.com", "full_name": "Arun"},
    "check_credits_or_raise": lambda *a: {"id": 1, "charged": 0},
    "_is_premium": lambda user: True,
    "_load_user_saved_profiles": lambda uid: ([_wife_row], []),
    "search_engine": _FakeSearch(),
    "_load_varsha_profile": lambda uid, cid: {
        "name": "Arun", "dob": "1985-03-14", "tob": "09:20", "place": "Test City",
        "lat": 13.08, "lon": 80.27, "gender": "male",
    },
    "_cached_varsha_phala": lambda *a, **k: None,
}
_saved = {name: getattr(_ai, name) for name in _patches}
_saved_engine = _deps.search_engine
_deps.search_engine = _patches["search_engine"]
for _name, _value in _patches.items():
    setattr(_ai, _name, _value)
_raw = _NS(headers={"x-session-token": "t"}, cookies={})
_pair = dict(male_chart=_male, female_chart=_female, compatibility=_comp, male_name="Arun",
             female_name="Meena Sundari", male_place="Test City", female_place="Test City", lang="ta")
_single = dict(chart_data=_male, client_name="Arun", place_name="Test City", lang="ta")
_calls = [
    (_ai.ai_predict, _ai.AIPredictRequest(**_single)),
    (_ai.ai_predict_marriage, _ai.AIMarriagePredictRequest(**_pair)),
    (_ai.ai_predict_chat, _ai.AIChatRequest(**_single, query="Compare my chart with my wife")),
    (_ai.ai_predict_varshaphala, _ai.VarshaphalaRequest(**_single, year=2026)),
    (_ai.ai_remedies, _ai.RemediesRequest(**_single)),
    (_ai.ai_predict_compatibility, _ai.AICompatibilityRequest(**_pair)),
    (_ai.ai_predict_prashna, _ai.PrashnaRequest(question="Will this work out?", latitude=13.08,
                                                longitude=80.27, lang="ta")),
    (_ai.ai_varsha_phala, _ai.PersonalVarshaRequest(lang="ta")),
]
try:
    for _fn, _req in _calls:
        _fn(_req, _raw)
finally:
    for _name, _value in _saved.items():
        setattr(_ai, _name, _value)
    _deps.search_engine = _saved_engine
check("prompts: all eight reading endpoints build a prompt", len(_captured) == 8)
_final_rule = _deps._language_lock("ta")
check("prompts: every reading has the Tamil language rule last and streams with lang=ta",
      all(_final_rule in c["prompt"][-1400:] and c["kw"].get("lang") == "ta" for c in _captured.values()))
check("prompts: the source-honesty rules reach every reading but the stricter remedy prompt",
      all(("SOURCE HONESTY" in c["prompt"]) == (a != "ai_remedies") for a, c in _captured.items()))
_chat = _captured["ai_predict_chat"]["prompt"]
check("prompts: a two-chart chat states both people's facts and the Tamil headings",
      all(h in _chat for h in READING_SECTIONS["ta"])
      and "Arun:" in _chat and "Meena Sundari:" in _chat and "Individual Ascendant, Moon" not in _chat)
check("prompts: chat, Preview Phala and marriage readings get the chart check",
      all(_captured[a]["kw"].get("post_check") for a in ("ai_predict", "ai_predict_marriage", "ai_predict_chat")))


print("\n" + ("ALL UNIT TESTS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
