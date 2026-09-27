from datetime import date

import pytest

from utm_tracker.visitors import Device, classify, referrer_host, visitor_hash

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
IPAD = "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
ANDROID_PHONE = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"
ANDROID_TABLET = "Mozilla/5.0 (Linux; Android 15; SM-X910) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


@pytest.mark.parametrize(
    ("ua", "device"),
    [
        (IPHONE, Device.MOBILE),
        (ANDROID_PHONE, Device.MOBILE),
        (IPAD, Device.TABLET),
        (ANDROID_TABLET, Device.TABLET),
        (DESKTOP, Device.DESKTOP),
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", Device.BOT),
        ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)", Device.BOT),
        ("Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)", Device.BOT),
        # Email security gateways that open every link before the recipient does.
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Proofpoint URL Defense", Device.BOT),
        ("Mimecast-URL-Protect/1.0", Device.BOT),
        ("Barracuda Sentinel (EE)", Device.BOT),
        ("curl/8.9.1", Device.BOT),
        ("", Device.BOT),
        (None, Device.BOT),
    ],
)
def test_classify(ua: str | None, device: Device) -> None:
    assert classify(ua) is device


@pytest.mark.parametrize(
    ("referrer", "host"),
    [
        ("https://www.linkedin.com/feed/", "linkedin.com"),
        ("https://mail.google.com/mail/u/0/", "mail.google.com"),
        ("android-app://com.google.android.gm/", "com.google.android.gm"),
        ("", None),
        (None, None),
    ],
)
def test_referrer_host(referrer: str | None, host: str | None) -> None:
    assert referrer_host(referrer) == host


def test_visitor_hash_is_stable_within_a_day_and_rotates_daily() -> None:
    day = date(2026, 9, 27)
    first = visitor_hash("s", day, "203.0.113.5", DESKTOP)

    assert first == visitor_hash("s", day, "203.0.113.5", DESKTOP)
    assert first != visitor_hash("s", date(2026, 9, 28), "203.0.113.5", DESKTOP)
    assert first != visitor_hash("s", day, "203.0.113.6", DESKTOP)
    assert first != visitor_hash("other-secret", day, "203.0.113.5", DESKTOP)
    assert "203.0.113.5" not in first
