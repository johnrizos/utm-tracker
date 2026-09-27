from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from utm_tracker.clicks import ClickInfo, record_click
from utm_tracker.config import Settings, get_settings
from utm_tracker.db import get_session, get_sessionmaker
from utm_tracker.models import Link

router = APIRouter(tags=["redirect"])


@router.get(
    "/r/{code}",
    summary="Follow a short link",
    status_code=status.HTTP_302_FOUND,
    responses={404: {"description": "Unknown code"}, 410: {"description": "Link archived"}},
)
def follow(
    code: str,
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    factory: Annotated[sessionmaker[Session], Depends(get_sessionmaker)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    link = session.scalar(select(Link).where(Link.code == code.lower()))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
    if link.archived:
        raise HTTPException(status.HTTP_410_GONE, detail="This link is no longer active.")

    background.add_task(
        record_click,
        factory,
        settings.visitor_secret,
        ClickInfo(
            link_id=link.id,
            at=datetime.now(UTC),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referrer=request.headers.get("referer"),
        ),
    )

    # 302, not 301: browsers cache permanent redirects and would skip us
    # (and the click count) on every later visit.
    return RedirectResponse(
        link.tagged_url,
        status_code=status.HTTP_302_FOUND,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer-when-downgrade"},
    )
