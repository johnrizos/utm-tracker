from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from utm_tracker.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class ApiKey(Base):
    """Each key is a separate workspace: it only sees the links it created."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # First characters, kept so a key can be recognized in a list without storing it.
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    links: Mapped[list["Link"]] = relationship(back_populates="owner")


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    destination_url: Mapped[str] = mapped_column(Text)
    tagged_url: Mapped[str] = mapped_column(Text)
    utm_source: Mapped[str] = mapped_column(String(100))
    utm_medium: Mapped[str] = mapped_column(String(100))
    utm_campaign: Mapped[str] = mapped_column(String(100), index=True)
    utm_term: Mapped[str | None] = mapped_column(String(100))
    utm_content: Mapped[str | None] = mapped_column(String(100))
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    owner: Mapped[ApiKey] = relationship(back_populates="links")
    clicks: Mapped[list["Click"]] = relationship(back_populates="link", passive_deletes=True)


class Click(Base):
    __tablename__ = "clicks"
    __table_args__ = (Index("ix_clicks_link_time", "link_id", "clicked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"))
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    device: Mapped[str] = mapped_column(String(10))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    referrer_host: Mapped[str | None] = mapped_column(String(255))
    visitor_hash: Mapped[str] = mapped_column(String(64))

    link: Mapped[Link] = relationship(back_populates="clicks")
