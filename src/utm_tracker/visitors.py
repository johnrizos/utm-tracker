"""Classifying and counting visitors without storing who they are."""

import hashlib
import re
from datetime import date
from enum import StrEnum
from urllib.parse import urlsplit


class Device(StrEnum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    TABLET = "tablet"
    BOT = "bot"


# Crawlers, link unfurlers, and above all the email security gateways that
# open every link in an incoming email before the recipient does. Without
# filtering them, an email campaign shows clicks from people who never saw it.
_BOTS = re.compile(
    r"bot|crawl|spider|slurp|preview|scanner|monitor|headless|python-requests|curl|wget|"
    r"facebookexternalhit|whatsapp|slackbot|discordbot|telegrambot|linkedinbot|"
    r"proofpoint|mimecast|barracuda|forcepoint|ironport|symantec|trendmicro|"
    r"microsoft office|safelinks|google-safety",
    re.IGNORECASE,
)
_TABLET = re.compile(r"ipad|tablet|kindle|silk|(android(?!.*mobile))", re.IGNORECASE)
_MOBILE = re.compile(r"mobi|iphone|ipod|android|windows phone", re.IGNORECASE)


def classify(user_agent: str | None) -> Device:
    ua = user_agent or ""
    # No user agent at all is almost always a script, not a person.
    if not ua.strip() or _BOTS.search(ua):
        return Device.BOT
    if _TABLET.search(ua):
        return Device.TABLET
    if _MOBILE.search(ua):
        return Device.MOBILE
    return Device.DESKTOP


def referrer_host(referrer: str | None) -> str | None:
    if not referrer:
        return None
    host = urlsplit(referrer).hostname
    return host.removeprefix("www.") if host else None


def visitor_hash(secret: str, day: date, ip: str | None, user_agent: str | None) -> str:
    """A daily-rotating fingerprint for counting unique visitors.

    The IP address is never stored. Because the date is part of the hash, the
    same person gets a different value tomorrow, so visits can't be linked
    across days. It's the approach privacy-focused analytics tools use.
    """
    material = f"{secret}|{day.isoformat()}|{ip or ''}|{user_agent or ''}"
    return hashlib.sha256(material.encode()).hexdigest()
