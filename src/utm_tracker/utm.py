"""Building and cleaning up UTM-tagged URLs.

Pure functions, no I/O, so the rules are easy to test and reuse.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")

# After normalizing, values are limited to what reads cleanly in any analytics tool.
_ALLOWED = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")
_SEPARATORS = re.compile(r"[\s_]+")


class UtmError(ValueError):
    """Raised with a message that is safe to show to the user."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass
class TaggedUrl:
    url: str
    params: dict[str, str]
    warnings: list[str] = field(default_factory=list)


def normalize_value(field: str, raw: str) -> tuple[str, str | None]:
    """Lowercase, trim and hyphenate a UTM value.

    Analytics tools treat "Facebook", "facebook" and "facebook " as three
    different sources, which splits one channel across several report rows.
    Returns the clean value and a warning when it had to change.
    """
    value = _SEPARATORS.sub("-", raw.strip().lower()).strip("-")

    if not value:
        raise UtmError(field, f"{field} can't be empty.")
    if len(value) > 100:
        raise UtmError(field, f"{field} is longer than 100 characters.")
    if not _ALLOWED.match(value):
        raise UtmError(
            field,
            f"{field} may only contain letters, numbers, '.', '-', '_' and '+'.",
        )

    warning = f'{field} "{raw}" was changed to "{value}".' if value != raw else None
    return value, warning


def build_tagged_url(destination: str, utm: Mapping[str, str | None]) -> TaggedUrl:
    """Add UTM parameters to a destination URL.

    Keeps the destination's own query parameters and fragment. UTM parameters
    already on the URL are replaced, with a warning, since two sets of tags on
    one link report unpredictably.
    """
    parts = urlsplit(destination.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise UtmError("destination_url", "Use a full http:// or https:// URL.")

    warnings: list[str] = []
    params: dict[str, str] = {}
    for name in UTM_FIELDS:
        raw = utm.get(name)
        if raw is None or raw.strip() == "":
            continue
        value, warning = normalize_value(name, raw)
        params[name] = value
        if warning:
            warnings.append(warning)

    for required in ("utm_source", "utm_medium", "utm_campaign"):
        if required not in params:
            raise UtmError(required, f"{required} is required.")

    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in UTM_FIELDS:
            warnings.append(f"The destination already had {key}={value}; it was replaced.")
            continue
        query.append((key, value))
    query.extend(params.items())

    url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "/", urlencode(query), parts.fragment)
    )
    return TaggedUrl(url=url, params=params, warnings=warnings)
