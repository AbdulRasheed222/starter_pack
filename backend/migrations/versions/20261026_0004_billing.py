"""billing module: plans and Stripe events

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("plan", sa.String(length=32), server_default="free", nullable=False),
    )
    op.add_column("workspaces", sa.Column("stripe_customer_id", sa.String(length=64)))
    op.add_column("workspaces", sa.Column("stripe_subscription_id", sa.String(length=64)))
    op.add_column("workspaces", sa.Column("subscription_status", sa.String(length=32)))
    op.create_unique_constraint(
        "workspaces_stripe_customer_id_key", "workspaces", ["stripe_customer_id"]
    )
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_constraint("workspaces_stripe_customer_id_key", "workspaces", type_="unique")
    op.drop_column("workspaces", "subscription_status")
    op.drop_column("workspaces", "stripe_subscription_id")
    op.drop_column("workspaces", "stripe_customer_id")
    op.drop_column("workspaces", "plan")
