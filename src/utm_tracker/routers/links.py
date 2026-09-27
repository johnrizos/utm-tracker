import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from utm_tracker.clicks import link_stats, period_start
from utm_tracker.config import Settings, get_settings
from utm_tracker.db import get_session
from utm_tracker.models import ApiKey, Click, Link
from utm_tracker.schemas import (
    CampaignRow,
    LinkCreate,
    LinkCreated,
    LinkOut,
    LinkPage,
    LinkStats,
    LinkUpdate,
)
from utm_tracker.security import require_api_key
from utm_tracker.utm import UtmError, build_tagged_url

router = APIRouter(prefix="/api")

Owner = Annotated[ApiKey, Depends(require_api_key)]
Db = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]

# No 0/O or 1/l/I: short codes get read aloud and retyped from print.
_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"
_CUSTOM_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{2,31}$")
_RESERVED = {"api", "docs", "health", "r", "redoc", "openapi"}


def _clicks_by_link() -> Select[int, int]:
    return (
        select(Click.link_id, func.count().label("clicks"))
        .where(Click.is_bot.is_(False))
        .group_by(Click.link_id)
    )


def _out(link: Link, clicks: int, settings: Settings) -> LinkOut:
    return LinkOut.model_validate(
        {
            **{c: getattr(link, c) for c in LinkOut.model_fields if hasattr(link, c)},
            "short_url": f"{settings.base_url.rstrip('/')}/r/{link.code}",
            "clicks": clicks,
        }
    )


def _get_owned(session: Session, owner: ApiKey, code: str) -> Link:
    link = session.scalar(select(Link).where(Link.code == code, Link.owner_id == owner.id))
    # Someone else's link looks exactly like a missing one.
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
    return link


def _new_code(session: Session) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(7))
        if session.scalar(select(Link.id).where(Link.code == code)) is None:
            return code
    raise RuntimeError("Could not find a free short code.")  # 32^7 codes; practically unreachable


@router.post(
    "/links", status_code=status.HTTP_201_CREATED, response_model=LinkCreated, tags=["links"]
)
def create_link(body: LinkCreate, owner: Owner, session: Db, settings: Config) -> LinkCreated:
    try:
        tagged = build_tagged_url(body.destination_url, body.model_dump())
    except UtmError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["body", e.field], "msg": e.message, "type": "value_error"}],
        ) from e

    if body.code is not None:
        code = body.code.strip().lower()
        if not _CUSTOM_CODE.match(code) or code in _RESERVED:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=[
                    {
                        "loc": ["body", "code"],
                        "msg": "Use 3-32 of a-z, 0-9 and '-'.",
                        "type": "value_error",
                    }
                ],
            )
        if session.scalar(select(Link.id).where(Link.code == code)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f'The code "{code}" is taken.')
    else:
        code = _new_code(session)

    link = Link(
        owner_id=owner.id,
        code=code,
        destination_url=body.destination_url.strip(),
        tagged_url=tagged.url,
        utm_source=tagged.params["utm_source"],
        utm_medium=tagged.params["utm_medium"],
        utm_campaign=tagged.params["utm_campaign"],
        utm_term=tagged.params.get("utm_term"),
        utm_content=tagged.params.get("utm_content"),
    )
    session.add(link)
    session.commit()

    return LinkCreated(**_out(link, 0, settings).model_dump(), warnings=tagged.warnings)


@router.get("/links", response_model=LinkPage, tags=["links"])
def list_links(
    owner: Owner,
    session: Db,
    settings: Config,
    campaign: str | None = None,
    source: str | None = None,
    medium: str | None = None,
    archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LinkPage:
    clicks = _clicks_by_link().subquery()
    query = (
        select(Link, func.coalesce(clicks.c.clicks, 0))
        .outerjoin(clicks, clicks.c.link_id == Link.id)
        .where(Link.owner_id == owner.id, Link.archived.is_(archived))
    )
    for column, value in (
        (Link.utm_campaign, campaign),
        (Link.utm_source, source),
        (Link.utm_medium, medium),
    ):
        if value:
            query = query.where(column == value.strip().lower())

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(Link.created_at.desc(), Link.id.desc()).limit(limit).offset(offset)
    )

    return LinkPage(
        items=[_out(link, n, settings) for link, n in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/links/{code}", response_model=LinkOut, tags=["links"])
def get_link(code: str, owner: Owner, session: Db, settings: Config) -> LinkOut:
    link = _get_owned(session, owner, code)
    clicks = session.scalar(
        select(func.count()).where(Click.link_id == link.id, Click.is_bot.is_(False))
    )
    return _out(link, clicks or 0, settings)


@router.patch("/links/{code}", response_model=LinkOut, tags=["links"])
def update_link(
    code: str, body: LinkUpdate, owner: Owner, session: Db, settings: Config
) -> LinkOut:
    """Archive or restore a link. Archived links answer 410 Gone; their history is kept."""
    link = _get_owned(session, owner, code)
    link.archived = body.archived
    session.commit()
    return get_link(code, owner, session, settings)


@router.get("/links/{code}/stats", response_model=LinkStats, tags=["links"])
def get_link_stats(
    code: str,
    owner: Owner,
    session: Db,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> LinkStats:
    return link_stats(session, _get_owned(session, owner, code), days)


@router.get("/campaigns", response_model=list[CampaignRow], tags=["campaigns"])
def campaign_report(
    owner: Owner,
    session: Db,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[CampaignRow]:
    """Clicks per campaign, source and medium: the table a marketing report starts from."""
    since = period_start(days)
    clicks = (
        select(
            Click.link_id,
            func.count().label("clicks"),
            func.count(Click.visitor_hash.distinct()).label("uniques"),
        )
        .where(Click.is_bot.is_(False), Click.clicked_at >= since)
        .group_by(Click.link_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Link.utm_campaign,
            Link.utm_source,
            Link.utm_medium,
            func.count(Link.id),
            func.coalesce(func.sum(clicks.c.clicks), 0),
            func.coalesce(func.sum(clicks.c.uniques), 0),
        )
        .outerjoin(clicks, clicks.c.link_id == Link.id)
        .where(Link.owner_id == owner.id)
        .group_by(Link.utm_campaign, Link.utm_source, Link.utm_medium)
        .order_by(func.coalesce(func.sum(clicks.c.clicks), 0).desc(), Link.utm_campaign)
    )

    return [
        CampaignRow(
            utm_campaign=campaign,
            utm_source=source,
            utm_medium=medium,
            links=links,
            clicks=int(n),
            unique_visitors=int(u),
        )
        for campaign, source, medium, links, n, u in rows
    ]
