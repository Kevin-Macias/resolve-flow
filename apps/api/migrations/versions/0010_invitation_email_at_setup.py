"""Let invitation recipients choose their email during account setup."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("auth_invitations", "email")


def downgrade() -> None:
    # Original email bindings cannot be recovered. Retire outstanding tokens
    # before restoring the old schema so rollback cannot assign a fake identity.
    op.add_column("auth_invitations", sa.Column("email", sa.Text(), nullable=True))
    op.execute(
        "UPDATE auth_invitations SET email = 'retired-' || id::text || "
        "'@example.invalid', revoked_at = COALESCE(revoked_at, now())"
    )
    op.alter_column("auth_invitations", "email", nullable=False)
