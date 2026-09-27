"""create api keys, links and clicks

Revision ID: 6e83acc764ad
Revises:
Create Date: 2026-09-27 17:50:09.570773

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e83acc764ad"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("destination_url", sa.Text(), nullable=False),
        sa.Column("tagged_url", sa.Text(), nullable=False),
        sa.Column("utm_source", sa.String(length=100), nullable=False),
        sa.Column("utm_medium", sa.String(length=100), nullable=False),
        sa.Column("utm_campaign", sa.String(length=100), nullable=False),
        sa.Column("utm_term", sa.String(length=100), nullable=True),
        sa.Column("utm_content", sa.String(length=100), nullable=True),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    with op.batch_alter_table("links", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_links_owner_id"), ["owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_links_utm_campaign"), ["utm_campaign"], unique=False)

    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device", sa.String(length=10), nullable=False),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("referrer_host", sa.String(length=255), nullable=True),
        sa.Column("visitor_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("clicks", schema=None) as batch_op:
        batch_op.create_index("ix_clicks_link_time", ["link_id", "clicked_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("clicks", schema=None) as batch_op:
        batch_op.drop_index("ix_clicks_link_time")

    op.drop_table("clicks")
    with op.batch_alter_table("links", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_links_utm_campaign"))
        batch_op.drop_index(batch_op.f("ix_links_owner_id"))

    op.drop_table("links")
    op.drop_table("api_keys")
