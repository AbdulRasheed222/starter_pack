"""billing jobs and document status

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26 13:28:00.971306
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "documents",
        sa.Column("status", sa.String(length=16), server_default="ready", nullable=False),
    )
    op.add_column("documents", sa.Column("error", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("content", sa.LargeBinary(), nullable=True))
    op.add_column(
        "workspaces", sa.Column("plan", sa.String(length=32), server_default="free", nullable=False)
    )
    op.add_column(
        "workspaces", sa.Column("stripe_customer_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "workspaces", sa.Column("stripe_subscription_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "workspaces", sa.Column("subscription_status", sa.String(length=32), nullable=True)
    )
    op.create_unique_constraint(
        "workspaces_stripe_customer_id_key", "workspaces", ["stripe_customer_id"]
    )


def downgrade() -> None:
    op.drop_constraint("workspaces_stripe_customer_id_key", "workspaces", type_="unique")
    op.drop_column("workspaces", "subscription_status")
    op.drop_column("workspaces", "stripe_subscription_id")
    op.drop_column("workspaces", "stripe_customer_id")
    op.drop_column("workspaces", "plan")
    op.drop_column("documents", "content")
    op.drop_column("documents", "error")
    op.drop_column("documents", "status")
    op.drop_table("stripe_events")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_table("jobs")
