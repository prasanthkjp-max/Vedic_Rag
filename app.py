"""Thin process entrypoint.

The actual FastAPI app is assembled in src/app.py from the routers in
src/api/*; this module just imports it and runs uvicorn, preserving the
documented `python3 app.py` launch command.

The re-exports below keep `import app; app.<name>` working for callers (the
test suite, tooling) that reach into internals that used to live directly in
this file before the app.py -> src/ split.
"""
from src.app import app

from src.core.config import (
    DB_PATH,
    REFERRAL_BONUS_REFEREE,
    REFERRAL_BONUS_REFERRER,
    SUBSCRIPTION_REFILL_CREDITS,
)
from src.api.deps import (
    _RATE_BUCKETS,
    _apply_referral,
    _is_key_protected,
    _safe_slug,
    check_credits_or_raise,
    debit_user_credits,
    rate_limit_or_raise,
    record_subscriber_usage,
    refund_user_credits,
)
from src.api.auth import _normalize_e164
from src.api.billing import (
    _apply_subscription_charge,
    _deactivate_subscription,
    _grant_credits_for_order,
    _grant_gift_for_order,
    _verify_payment_signature,
    _verify_subscription_signature,
    _verify_webhook_signature,
    billing_usage,
)
from src.api.chart import (
    _build_premium_report,
    _fail_and_refund_report,
    _reap_stranded_reports,
    _sign_report_token,
    _verify_report_token,
)
from src.api.panchangam import _tithi_num
from src.api.public import _source_archive_path, liveness_probe

if __name__ == "__main__":
    import uvicorn
    # Run uvicorn on port 8008
    uvicorn.run("app:app", host="0.0.0.0", port=8008, reload=False)
