"""Recording clicks and reading them back as statistics."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from utm_tracker.models import Click, Link
from utm_tracker.schemas import DailyClicks, LinkStats, ReferrerCount
from utm_tracker.visitors import Device, classify, referrer_host, visitor_hash


@dataclass(frozen=True)
class ClickInfo:
    link_id: int
    at: datetime
    ip: str | None
    user_agent: str | None
    referrer: str | None


def record_click(factory: sessionmaker[Session], secret: str, info: ClickInfo) -> None:
    """Runs after the redirect has been sent, so visitors never wait on the database."""
    device = classify(info.user_agent)
    with factory() as session:
        session.add(
            Click(
                link_id=info.link_id,
                clicked_at=info.at,
                device=device.value,
                is_bot=device is Device.BOT,
                referrer_host=referrer_host(info.referrer),
                visitor_hash=visitor_hash(secret, info.at.date(), info.ip, info.user_agent),
            )
        )
        session.commit()


def period_start(days: int) -> datetime:
    """Midnight UTC at the start of a window of `days` days that ends today."""
    today = datetime.now(UTC).date()
    return datetime.combine(today - timedelta(days=days - 1), time.min, tzinfo=UTC)


def _as_date(value: object) -> date:
    # func.date() gives a string on SQLite and a date on PostgreSQL.
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def link_stats(session: Session, link: Link, days: int) -> LinkStats:
    since = period_start(days)
    in_period = (Click.link_id == link.id, Click.clicked_at >= since)
    human = (*in_period, Click.is_bot.is_(False))
    day = func.date(Click.clicked_at)

    by_day: dict[date, tuple[int, int]] = {
        _as_date(d): (clicks, uniques)
        for d, clicks, uniques in session.execute(
            select(day, func.count(), func.count(Click.visitor_hash.distinct()))
            .where(*human)
            .group_by(day)
        )
    }
    daily = [
        DailyClicks(date=current, clicks=clicks, unique_visitors=uniques)
        for current in (since.date() + timedelta(days=i) for i in range(days))
        for clicks, uniques in [by_day.get(current, (0, 0))]
    ]

    devices = {d.value: 0 for d in Device if d is not Device.BOT}
    for device, count in session.execute(
        select(Click.device, func.count()).where(*human).group_by(Click.device)
    ):
        devices[device] = count

    referrers = [
        ReferrerCount(host=host, clicks=count)
        for host, count in session.execute(
            select(Click.referrer_host, func.count())
            .where(*human, Click.referrer_host.is_not(None))
            .group_by(Click.referrer_host)
            .order_by(func.count().desc(), Click.referrer_host)
            .limit(10)
        )
        if host is not None
    ]

    return LinkStats(
        code=link.code,
        since=since.date(),
        until=datetime.now(UTC).date(),
        clicks=sum(d.clicks for d in daily),
        unique_visitors=sum(d.unique_visitors for d in daily),
        bot_clicks=session.scalar(select(func.count()).where(*in_period, Click.is_bot.is_(True)))
        or 0,
        daily=daily,
        devices=devices,
        referrers=referrers,
    )
