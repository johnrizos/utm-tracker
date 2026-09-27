from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from utm_tracker.models import ApiKey, Click, Link

DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Safari/604.1"

LINK = {
    "destination_url": "https://shop.example.com/autumn?ref=nav",
    "utm_source": "newsletter",
    "utm_medium": "email",
    "utm_campaign": "autumn-sale",
}


def create(client: TestClient, auth: dict[str, str], **overrides: Any) -> dict[str, Any]:
    response = client.post("/api/links", json={**LINK, **overrides}, headers=auth)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


# --- auth -------------------------------------------------------------------


def test_management_endpoints_need_a_valid_key(
    client: TestClient, session: Session, auth: dict[str, str]
) -> None:
    assert client.get("/api/links").status_code == 401
    assert client.get("/api/links", headers={"X-API-Key": "utm_nope"}).status_code == 401

    key = session.scalars(select(ApiKey)).one()
    key.revoked_at = datetime.now(UTC)
    session.commit()

    response = client.get("/api/links", headers=auth)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "ApiKey"


# --- creating links ---------------------------------------------------------


def test_create_link(client: TestClient, auth: dict[str, str]) -> None:
    link = create(client, auth, utm_source="Facebook Ads", utm_content="Hero Button")

    assert link["short_url"] == f"https://go.example.com/r/{link['code']}"
    assert len(link["code"]) == 7
    assert link["utm_source"] == "facebook-ads"
    assert link["tagged_url"] == (
        "https://shop.example.com/autumn?ref=nav&utm_source=facebook-ads&utm_medium=email"
        "&utm_campaign=autumn-sale&utm_content=hero-button"
    )
    assert link["warnings"] == [
        'utm_source "Facebook Ads" was changed to "facebook-ads".',
        'utm_content "Hero Button" was changed to "hero-button".',
    ]
    assert link["clicks"] == 0


def test_validation_errors_point_at_the_field(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post(
        "/api/links", json={**LINK, "destination_url": "shop.example.com"}, headers=auth
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "destination_url"]


def test_custom_codes(client: TestClient, auth: dict[str, str], other_auth: dict[str, str]) -> None:
    assert create(client, auth, code="Autumn")["code"] == "autumn"

    # Codes are global because they share one /r/ namespace.
    assert (
        client.post("/api/links", json={**LINK, "code": "autumn"}, headers=other_auth).status_code
        == 409
    )
    for bad in ("ab", "docs", "has space", "-leading"):
        assert (
            client.post("/api/links", json={**LINK, "code": bad}, headers=auth).status_code == 422
        )


# --- listing and ownership --------------------------------------------------


def test_list_filters_and_paginates(
    client: TestClient, auth: dict[str, str], other_auth: dict[str, str]
) -> None:
    create(client, auth, utm_campaign="autumn-sale")
    create(
        client, auth, utm_campaign="autumn-sale", utm_source="facebook", utm_medium="paid-social"
    )
    create(client, auth, utm_campaign="black-friday")
    create(client, other_auth, utm_campaign="autumn-sale")

    everything = client.get("/api/links", headers=auth).json()
    assert everything["total"] == 3

    autumn = client.get("/api/links", params={"campaign": "Autumn-Sale"}, headers=auth).json()
    assert {i["utm_source"] for i in autumn["items"]} == {"newsletter", "facebook"}

    page = client.get("/api/links", params={"limit": 2, "offset": 2}, headers=auth).json()
    assert (page["total"], len(page["items"])) == (3, 1)


def test_other_keys_cannot_see_or_change_a_link(
    client: TestClient, auth: dict[str, str], other_auth: dict[str, str]
) -> None:
    code = create(client, auth)["code"]

    assert client.get(f"/api/links/{code}", headers=other_auth).status_code == 404
    assert client.get(f"/api/links/{code}/stats", headers=other_auth).status_code == 404
    assert (
        client.patch(f"/api/links/{code}", json={"archived": True}, headers=other_auth).status_code
        == 404
    )
    assert client.get(f"/api/links/{code}", headers=auth).json()["archived"] is False


# --- redirect ---------------------------------------------------------------


def test_redirect_counts_people_but_not_bots(
    client: TestClient, auth: dict[str, str], session: Session
) -> None:
    link = create(client, auth)

    response = client.get(
        f"/r/{link['code']}", headers={"user-agent": IPHONE, "referer": "https://www.linkedin.com/"}
    )
    assert response.status_code == 302
    assert response.headers["location"] == link["tagged_url"]
    assert response.headers["cache-control"] == "no-store"

    client.get(f"/r/{link['code']}", headers={"user-agent": "Mimecast-URL-Protect/1.0"})

    clicks = session.scalars(select(Click).order_by(Click.id)).all()
    assert [(c.device, c.is_bot, c.referrer_host) for c in clicks] == [
        ("mobile", False, "linkedin.com"),
        ("bot", True, None),
    ]
    assert client.get(f"/api/links/{link['code']}", headers=auth).json()["clicks"] == 1


def test_unknown_and_archived_links(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/r/nothere").status_code == 404

    code = create(client, auth)["code"]
    assert (
        client.patch(f"/api/links/{code}", json={"archived": True}, headers=auth).json()["archived"]
        is True
    )
    assert client.get(f"/r/{code}").status_code == 410

    archived = client.get("/api/links", params={"archived": True}, headers=auth).json()
    assert [i["code"] for i in archived["items"]] == [code]


# --- statistics -------------------------------------------------------------


def add_click(session: Session, link_id: int, days_ago: int, visitor: str, **kwargs: Any) -> None:
    at = datetime.now(UTC).replace(hour=12) - timedelta(days=days_ago)
    session.add(
        Click(
            link_id=link_id,
            clicked_at=at,
            device=kwargs.get("device", "desktop"),
            is_bot=kwargs.get("is_bot", False),
            referrer_host=kwargs.get("referrer"),
            visitor_hash=visitor,
        )
    )
    session.commit()


def test_link_stats(client: TestClient, auth: dict[str, str], session: Session) -> None:
    link = create(client, auth)
    link_id = session.scalars(select(Link.id)).one()

    add_click(session, link_id, 0, "a", referrer="linkedin.com")
    add_click(session, link_id, 0, "a", referrer="linkedin.com")  # same visitor, same day
    add_click(session, link_id, 0, "b", device="mobile", referrer="mail.google.com")
    add_click(session, link_id, 2, "a", device="mobile")
    add_click(session, link_id, 1, "bot", device="bot", is_bot=True)
    add_click(session, link_id, 40, "old")  # outside the window

    stats = client.get(f"/api/links/{link['code']}/stats", params={"days": 7}, headers=auth).json()

    assert (stats["clicks"], stats["unique_visitors"], stats["bot_clicks"]) == (4, 3, 1)
    assert len(stats["daily"]) == 7
    assert [(d["clicks"], d["unique_visitors"]) for d in stats["daily"][-3:]] == [
        (1, 1),
        (0, 0),
        (3, 2),
    ]
    assert stats["devices"] == {"desktop": 2, "mobile": 2, "tablet": 0}
    assert stats["referrers"] == [
        {"host": "linkedin.com", "clicks": 2},
        {"host": "mail.google.com", "clicks": 1},
    ]


def test_campaign_report(client: TestClient, auth: dict[str, str], session: Session) -> None:
    create(client, auth, utm_content="header")
    create(client, auth, utm_content="footer")
    create(client, auth, utm_source="facebook", utm_medium="paid-social")
    ids = session.scalars(select(Link.id).order_by(Link.id)).all()

    for link_id, visitor in ((ids[0], "a"), (ids[0], "b"), (ids[1], "a"), (ids[2], "c")):
        add_click(session, link_id, 0, visitor)
    add_click(session, ids[2], 0, "bot", is_bot=True)

    rows = client.get("/api/campaigns", headers=auth).json()

    assert rows == [
        {
            "utm_campaign": "autumn-sale",
            "utm_source": "newsletter",
            "utm_medium": "email",
            "links": 2,
            "clicks": 3,
            "unique_visitors": 3,
        },
        {
            "utm_campaign": "autumn-sale",
            "utm_source": "facebook",
            "utm_medium": "paid-social",
            "links": 1,
            "clicks": 1,
            "unique_visitors": 1,
        },
    ]


@pytest.mark.parametrize("days", [0, 366])
def test_stats_window_is_bounded(client: TestClient, auth: dict[str, str], days: int) -> None:
    code = create(client, auth)["code"]
    assert (
        client.get(f"/api/links/{code}/stats", params={"days": days}, headers=auth).status_code
        == 422
    )
