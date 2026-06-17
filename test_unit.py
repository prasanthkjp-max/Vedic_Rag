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
check("liveness: /api/live is an open (no-key) path", "/api/live" in app._OPEN_API_PATHS)

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

print("\n" + ("ALL UNIT TESTS PASS" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
