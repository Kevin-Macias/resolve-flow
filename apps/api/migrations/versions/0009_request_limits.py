"""Shared fixed request windows with no raw identity or request content."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE request_limit_windows (
            key_hash TEXT NOT NULL,
            resets_at TIMESTAMPTZ NOT NULL,
            attempts INTEGER NOT NULL,
            CONSTRAINT pk_request_limit_windows PRIMARY KEY (key_hash),
            CONSTRAINT ck_request_limit_windows_attempts CHECK (attempts > 0),
            CONSTRAINT ck_request_limit_windows_key_hash CHECK (key_hash ~ '^[0-9a-f]{64}$')
        )
    """)
    op.create_index(
        "ix_request_limit_windows_resets_at", "request_limit_windows", ["resets_at"]
    )


def downgrade() -> None:
    op.drop_table("request_limit_windows")
