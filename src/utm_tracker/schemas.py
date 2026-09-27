from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LinkCreate(BaseModel):
    destination_url: str = Field(examples=["https://shop.example.com/autumn?ref=nav"])
    utm_source: str = Field(examples=["newsletter"])
    utm_medium: str = Field(examples=["email"])
    utm_campaign: str = Field(examples=["autumn-sale-2026"])
    utm_term: str | None = None
    utm_content: str | None = Field(default=None, examples=["hero-button"])
    code: str | None = Field(
        default=None,
        description="Custom short code (3-32 of a-z, 0-9 and '-'). Random if omitted.",
        examples=["autumn"],
    )


class LinkUpdate(BaseModel):
    archived: bool


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    short_url: str
    destination_url: str
    tagged_url: str
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_term: str | None
    utm_content: str | None
    archived: bool
    created_at: datetime
    clicks: int = Field(description="Human clicks, bots excluded.")


class LinkCreated(LinkOut):
    warnings: list[str] = Field(description="What was changed to keep the tags consistent.")


class LinkPage(BaseModel):
    items: list[LinkOut]
    total: int
    limit: int
    offset: int


class DailyClicks(BaseModel):
    date: date
    clicks: int
    unique_visitors: int


class ReferrerCount(BaseModel):
    host: str
    clicks: int


class LinkStats(BaseModel):
    code: str
    since: date
    until: date
    clicks: int
    unique_visitors: int = Field(
        description="Distinct visitors per day, summed: someone clicking on two days counts twice."
    )
    bot_clicks: int = Field(
        description="Filtered out: crawlers, link previews and email security scanners."
    )
    daily: list[DailyClicks]
    devices: dict[str, int]
    referrers: list[ReferrerCount]


class CampaignRow(BaseModel):
    utm_campaign: str
    utm_source: str
    utm_medium: str
    links: int
    clicks: int
    unique_visitors: int
