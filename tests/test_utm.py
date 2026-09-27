from urllib.parse import parse_qs, urlsplit

import pytest

from utm_tracker.utm import UtmError, build_tagged_url, normalize_value

BASE = {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "autumn-sale"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("newsletter", "newsletter"),
        ("Facebook", "facebook"),
        ("  Paid Social ", "paid-social"),
        ("autumn_sale 2026", "autumn-sale-2026"),
        ("cpc", "cpc"),
        ("v1.2+beta", "v1.2+beta"),
    ],
)
def test_normalize_value(raw: str, expected: str) -> None:
    value, warning = normalize_value("utm_source", raw)
    assert value == expected
    assert (warning is None) == (raw == expected)


@pytest.mark.parametrize("raw", ["", "   ", "---", "naïve", "a/b", "x" * 101])
def test_normalize_value_rejects(raw: str) -> None:
    with pytest.raises(UtmError) as err:
        normalize_value("utm_medium", raw)
    assert err.value.field == "utm_medium"


def test_keeps_the_destination_query_and_fragment() -> None:
    tagged = build_tagged_url("https://shop.example.com/sale?ref=nav&color=red#top", BASE)

    parts = urlsplit(tagged.url)
    assert parts.path == "/sale"
    assert parts.fragment == "top"
    assert parse_qs(parts.query) == {
        "ref": ["nav"],
        "color": ["red"],
        "utm_source": ["newsletter"],
        "utm_medium": ["email"],
        "utm_campaign": ["autumn-sale"],
    }
    assert tagged.warnings == []


def test_replaces_existing_utm_tags_with_a_warning() -> None:
    tagged = build_tagged_url("https://example.com/?utm_source=old&UTM_MEDIUM=x", BASE)

    assert parse_qs(urlsplit(tagged.url).query)["utm_source"] == ["newsletter"]
    assert len(tagged.warnings) == 2


def test_optional_fields_and_warnings() -> None:
    tagged = build_tagged_url(
        "https://example.com",
        {**BASE, "utm_source": "Facebook", "utm_content": "Hero Button", "utm_term": None},
    )

    assert tagged.params["utm_content"] == "hero-button"
    assert "utm_term" not in tagged.params
    assert urlsplit(tagged.url).path == "/"
    assert tagged.warnings == [
        'utm_source "Facebook" was changed to "facebook".',
        'utm_content "Hero Button" was changed to "hero-button".',
    ]


@pytest.mark.parametrize(
    "url", ["example.com/page", "ftp://example.com/file", "/relative", "https://"]
)
def test_rejects_urls_that_are_not_absolute_http(url: str) -> None:
    with pytest.raises(UtmError) as err:
        build_tagged_url(url, BASE)
    assert err.value.field == "destination_url"


def test_source_medium_and_campaign_are_required() -> None:
    with pytest.raises(UtmError) as err:
        build_tagged_url("https://example.com", {**BASE, "utm_campaign": "  "})
    assert err.value.field == "utm_campaign"
