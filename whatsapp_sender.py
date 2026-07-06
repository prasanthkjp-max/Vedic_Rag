import logging
import httpx
import os
import hmac
import hashlib
from config import (
    WHATSAPP_TOKEN,
    WHATSAPP_PHONE_ID,
    WHATSAPP_ENABLED,
    WHATSAPP_TEMPLATE_REPORT_READY,
    WHATSAPP_TEMPLATE_DAILY_DIGEST,
    WHATSAPP_WEBHOOK_SECRET
)

logger = logging.getLogger("vedic.whatsapp")


def verify_whatsapp_signature(payload: bytes, signature_header: str) -> bool:
    """
    Verify X-Hub-Signature-256 header using WHATSAPP_WEBHOOK_SECRET.
    """
    secret = WHATSAPP_WEBHOOK_SECRET
    if not secret:
        logger.warning("WhatsApp Webhook secret not configured. Signature verification failed.")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    received_sig = signature_header[7:]
    expected_sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received_sig, expected_sig)


def send_whatsapp_template(to_phone: str, template_name: str, language_code: str, components: list) -> bool:
    """
    Send a WhatsApp template message using Meta WhatsApp Cloud API.
    """
    if not WHATSAPP_ENABLED:
        logger.info("WhatsApp delivery is disabled (WHATSAPP_ENABLED=0). Message not sent.")
        return False
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        logger.warning("WhatsApp token or Phone ID not configured. Message not sent.")
        return False

    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    # Format destination phone to E.164 (without leading + for Meta API)
    clean_phone = "".join(c for c in to_phone if c.isdigit())
    if not clean_phone:
        logger.warning("No valid digits found in destination phone: %s", to_phone)
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code
            },
            "components": components
        }
    }

    try:
        # Respect outbound proxy (httpx handles environment variables HTTP_PROXY/HTTPS_PROXY/NO_PROXY by default)
        with httpx.Client(trust_env=True) as client:
            response = client.post(url, headers=headers, json=payload, timeout=10.0)
            if response.status_code in (200, 201):
                logger.info("WhatsApp template message sent successfully to %s", clean_phone)
                return True
            else:
                logger.error("WhatsApp API returned error %d: %s", response.status_code, response.text)
                return False
    except Exception as e:
        logger.error("Failed to send WhatsApp message: %s", e)
        return False


def send_report_ready_notification(to_phone: str, lang: str, client_name: str, download_url: str) -> bool:
    """
    Send a report_ready template message.
    """
    template_name = WHATSAPP_TEMPLATE_REPORT_READY.get(lang, WHATSAPP_TEMPLATE_REPORT_READY.get("en", "report_ready_en"))
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": client_name},
                {"type": "text", "text": download_url}
            ]
        }
    ]
    return send_whatsapp_template(to_phone, template_name, lang, components)


def send_daily_digest_notification(to_phone: str, lang: str, client_name: str, digest_text: str) -> bool:
    """
    Send a daily_digest template message.
    """
    template_name = WHATSAPP_TEMPLATE_DAILY_DIGEST.get(lang, WHATSAPP_TEMPLATE_DAILY_DIGEST.get("en", "daily_digest_en"))
    # Truncate text if too long
    short_text = digest_text[:900]
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": client_name},
                {"type": "text", "text": short_text}
            ]
        }
    ]
    return send_whatsapp_template(to_phone, template_name, lang, components)
