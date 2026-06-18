import logging
import requests
from datetime import datetime

log = logging.getLogger(__name__)

CAPTCHA_PATTERNS = [
    'captcha',
    'verify you are human',
    'too many attempts',
    'security verification',
    'confirm you\'re not a bot',
]

LOGIN_PATTERNS = [
    'Log in to TikTok',
    'login-container',
]

RATE_LIMIT_PATTERNS = [
    'too fast',
    'rate limit',
    'slow down',
    'try again later',
]


def check_page(page) -> str | None:
    """Check current page for captcha, login, or rate-limit. Returns problem type or None."""
    try:
        url = page.url.lower()
        for p in CAPTCHA_PATTERNS:
            if p in url:
                log.warning("CAPTCHA detected in URL: %s", page.url)
                return "captcha"

        body_text = page.text_content("body", timeout=3000) or ""
        body_lower = body_text.lower()

        for p in CAPTCHA_PATTERNS:
            if p in body_lower:
                log.warning("CAPTCHA detected on page")
                return "captcha"

        for p in LOGIN_PATTERNS:
            if p in body_lower:
                log.warning("Login required detected on page")
                return "login_required"

        for p in RATE_LIMIT_PATTERNS:
            if p in body_lower:
                log.warning("Rate limit detected on page")
                return "rate_limited"

    except Exception as e:
        log.debug("Sentinel check failed: %s", e)

    return None


def notify(message: str, webhook_url: str | None = None):
    """Send notification via webhook or log."""
    if not webhook_url:
        log.info("NOTIFY: %s", message)
        return

    try:
        payload = {
            "content": f"🔥 FlameKeeper Alert — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{message}"
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        log.error("Failed to send notification: %s", e)
