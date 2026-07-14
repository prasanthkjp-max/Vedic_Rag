#!/usr/bin/env python3
"""
Send the daily personalized transit digest to every opted-in user.

Cron-invoked, standalone (never runs inside the web process):

    30 6 * * *  cd /path/to/Vedic_Rag && set -a && . ./.env && set +a && python3 tools/send_digests.py

Delivery is SMTP (config VEDIC_SMTP_*); with SMTP unconfigured the script
fails closed — it logs and exits without touching any subscription. Astro
Pass subscribers optionally get their digest rewritten once by MODEL_FAST
(VEDIC_DIGEST_LLM=0 disables); the deterministic text is always the fallback,
so an LLM outage degrades tone, never delivery.

    --dry-run   render and print instead of sending (marks nothing sent)
    --date      YYYY-MM-DD to render for (default: today)
    --email     only this user (testing)
"""
import os
import sys
import argparse
import logging
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (  # noqa: E402
    DB_PATH,
    connect_db,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
    SMTP_ENABLED,
    DIGEST_LLM_ENABLED,
    MODEL_FAST,
    OPENROUTER_API_KEY,
    get_llm_client,
    PORTAL_BASE_URL,
)
from digest_engine import build_digest, LABELS  # noqa: E402

logger = logging.getLogger("vedic.send_digests")

_UNSUB_LABEL = {
    "en": "Unsubscribe", "ta": "விலகிக்கொள்ள", "te": "అన్‌సబ్స్క్రైబ్",
    "ml": "അൺസബ്സ്ക്രൈബ്", "kn": "ಅನ್‌ಸಬ್‌ಸ್ಕ್ರೈಬ್", "hi": "सदस्यता रद्द करें",
}


def _fetch_recipients(conn, only_email=None):
    """Opted-in users with complete birth data. Users without dob/tob are
    skipped (the subscribe endpoint requires them, but profiles can be
    edited afterwards)."""
    sql = (
        # Natal charts need the BIRTH coordinates (birth_*); the legacy
        # latitude/longitude are the user's current location and only serve
        # as a fallback for profiles saved before the birth_* split.
        "SELECT u.id, u.email, u.full_name, u.dob, u.tob, "
        "       COALESCE(u.birth_latitude, u.latitude), COALESCE(u.birth_longitude, u.longitude), "
        "       d.language, d.unsubscribe_token, d.last_sent_date, "
        "       EXISTS(SELECT 1 FROM subscriptions s WHERE s.user_id = u.id "
        "              AND s.status = 'active' AND s.current_period_end > ?) AS is_subscriber "
        "FROM digest_subscriptions d JOIN users u ON u.id = d.user_id "
        "WHERE d.enabled = 1"
    )
    params = [datetime.utcnow().isoformat()]
    if only_email:
        sql += " AND u.email = ?"
        params.append(only_email)
    return conn.execute(sql, params).fetchall()


def _llm_polish(text, lang):
    """One MODEL_FAST call to soften the deterministic digest for subscribers.
    Any failure returns the original text."""
    if not (DIGEST_LLM_ENABLED and OPENROUTER_API_KEY):
        return text
    lang_names = {"en": "English", "ta": "Tamil", "te": "Telugu",
                  "ml": "Malayalam", "kn": "Kannada", "hi": "Hindi"}
    prompt = (
        "Rewrite this daily Vedic astrology digest as a short, warm, encouraging "
        f"message in {lang_names.get(lang, 'English')}. Keep EVERY fact, number, name and time window "
        "exactly as given — do not add, drop, or alter any astrological data. Keep it under "
        "180 words, plain text, no markdown headings.\n\n" + text
    )
    try:
        resp = get_llm_client().with_options(timeout=60).chat.completions.create(
            model=MODEL_FAST, messages=[{"role": "user", "content": prompt}]
        )
        polished = (resp.choices[0].message.content or "").strip()
        return polished or text
    except Exception as e:
        logger.warning("LLM polish failed, sending deterministic text: %s", e)
        return text


def _send_email(to_email, subject, body):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Vedic Astro AI", SMTP_FROM))
    msg["To"] = to_email
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    try:
        if SMTP_PORT != 465:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass  # plain relay (e.g. localhost postfix)
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())
    finally:
        server.quit()


def main():
    parser = argparse.ArgumentParser(description="Send daily transit digests")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--date", help="YYYY-MM-DD to render for (default today)")
    parser.add_argument("--email", help="send only to this user's email")
    args = parser.parse_args()

    ref_date = date.fromisoformat(args.date) if args.date else date.today()

    if not SMTP_ENABLED and not args.dry_run:
        logger.error(
            "SMTP is not configured (set VEDIC_SMTP_HOST / VEDIC_SMTP_FROM) — nothing sent."
        )
        return 1

    conn = connect_db(DB_PATH)
    try:
        recipients = _fetch_recipients(conn, args.email)
    finally:
        conn.close()

    sent = skipped = failed = 0
    for (uid, email, full_name, dob, tob, lat, lon,
         lang, unsub_token, last_sent, is_subscriber) in recipients:
        if not (dob and tob and email) or "@phone.auth" in email:
            skipped += 1
            continue
        if last_sent == ref_date.isoformat() and not args.dry_run:
            skipped += 1  # already delivered today (cron re-run)
            continue
        lang = lang if lang in LABELS else "en"
        try:
            digest = build_digest(full_name or "Friend", dob, tob, lat, lon, lang, ref_date)
        except Exception as e:
            logger.error("Digest build failed for user %s: %s", uid, e)
            failed += 1
            continue

        body = digest["text"]
        if is_subscriber:
            body = _llm_polish(body, lang)
        body += (
            f"\n\n—\n{_UNSUB_LABEL.get(lang, 'Unsubscribe')}: "
            f"{PORTAL_BASE_URL}/digest/unsubscribe/{unsub_token}\n"
        )

        if args.dry_run:
            print(f"=== {email} [{lang}]{' (subscriber)' if is_subscriber else ''} ===")
            print(f"Subject: {digest['subject']}\n{body}\n")
            sent += 1
            continue

        try:
            _send_email(email, digest["subject"], body)
            conn = connect_db(DB_PATH)
            try:
                conn.execute(
                    "UPDATE digest_subscriptions SET last_sent_date = ? WHERE user_id = ?",
                    (ref_date.isoformat(), uid),
                )
                conn.commit()
            finally:
                conn.close()
            sent += 1
        except Exception as e:
            logger.error("Send failed for %s: %s", email, e)
            failed += 1

    logger.info("Digest run complete: sent=%d skipped=%d failed=%d", sent, skipped, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
