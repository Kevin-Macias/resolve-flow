"""Create the initial issue-report schema.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID as PythonUUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def id_column() -> sa.Column[PythonUUID]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def timestamp_columns() -> tuple[sa.Column[datetime], sa.Column[datetime]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "customer_accounts",
        id_column(),
        sa.Column("name", sa.Text(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_accounts"),
    )
    op.create_table(
        "services",
        id_column(),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint("code", name="uq_services_code"),
    )
    op.create_table(
        "users",
        id_column(),
        sa.Column("customer_account_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "(user_type = 'customer' AND customer_account_id IS NOT NULL) "
            "OR (user_type = 'support' AND customer_account_id IS NULL)",
            name=op.f("ck_users_user_type_account"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            name="fk_users_customer_account_id_customer_accounts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_customer_account_id", "users", ["customer_account_id"])
    op.create_table(
        "issue_reports",
        id_column(),
        sa.Column("customer_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("affected_service_id", postgresql.UUID(as_uuid=True)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *timestamp_columns(),
        sa.CheckConstraint(
            "char_length(btrim(description)) BETWEEN 1 AND 5000",
            name=op.f("ck_issue_reports_description_length"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'in_review', 'linked', 'deleted', 'closed')",
            name=op.f("ck_issue_reports_status"),
        ),
        sa.ForeignKeyConstraint(
            ["customer_account_id"],
            ["customer_accounts.id"],
            name="fk_issue_reports_customer_account_id_customer_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            name="fk_issue_reports_submitted_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["affected_service_id"],
            ["services.id"],
            name="fk_issue_reports_affected_service_id_services",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_issue_reports"),
    )
    op.create_index(
        "ix_issue_reports_customer_account_id", "issue_reports", ["customer_account_id"]
    )
    op.create_index(
        "ix_issue_reports_submitted_by_user_id",
        "issue_reports",
        ["submitted_by_user_id"],
    )
    op.create_index(
        "ix_issue_reports_affected_service_id",
        "issue_reports",
        ["affected_service_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_issue_reports_affected_service_id", table_name="issue_reports")
    op.drop_index("ix_issue_reports_submitted_by_user_id", table_name="issue_reports")
    op.drop_index("ix_issue_reports_customer_account_id", table_name="issue_reports")
    op.drop_table("issue_reports")
    op.drop_index("ix_users_customer_account_id", table_name="users")
    op.drop_table("users")
    op.drop_table("services")
    op.drop_table("customer_accounts")
