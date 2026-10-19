"""Add invitation enrollment, permanent credentials, and revocable sessions."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE auth_credentials (
            user_id UUID NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL,
            disabled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_auth_credentials PRIMARY KEY (user_id),
            CONSTRAINT uq_auth_credentials_email UNIQUE (email),
            CONSTRAINT fk_auth_credentials_user_id_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE auth_sessions (
            id UUID NOT NULL,
            user_id UUID NOT NULL,
            token_hash TEXT NOT NULL,
            user_type TEXT NOT NULL,
            customer_account_id UUID,
            is_admin BOOLEAN NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_auth_sessions PRIMARY KEY (id),
            CONSTRAINT uq_auth_sessions_token_hash UNIQUE (token_hash),
            CONSTRAINT fk_auth_sessions_user_id_auth_credentials FOREIGN KEY (user_id) REFERENCES auth_credentials(user_id) ON DELETE RESTRICT,
            CONSTRAINT fk_auth_sessions_customer_account_id_customer_accounts FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id) ON DELETE RESTRICT,
            CONSTRAINT ck_auth_sessions_token_hash CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_auth_sessions_user_type_account CHECK ((user_type = 'customer' AND customer_account_id IS NOT NULL) OR (user_type = 'support' AND customer_account_id IS NULL))
        )
    """)
    op.execute("""
        CREATE TABLE auth_invitations (
            id UUID NOT NULL,
            email TEXT NOT NULL,
            user_type TEXT NOT NULL,
            customer_account_id UUID,
            support_account_ids JSONB NOT NULL,
            token_hash TEXT NOT NULL,
            created_by UUID NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_auth_invitations PRIMARY KEY (id),
            CONSTRAINT uq_auth_invitations_token_hash UNIQUE (token_hash),
            CONSTRAINT fk_auth_invitations_customer_account_id_customer_accounts FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id) ON DELETE RESTRICT,
            CONSTRAINT fk_auth_invitations_created_by_auth_credentials FOREIGN KEY (created_by) REFERENCES auth_credentials(user_id) ON DELETE RESTRICT,
            CONSTRAINT ck_auth_invitations_token_hash CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_auth_invitations_user_type_account CHECK ((user_type = 'customer' AND customer_account_id IS NOT NULL) OR (user_type = 'support' AND customer_account_id IS NULL))
        )
    """)
    op.execute("""
        CREATE TABLE support_account_grants (
            user_id UUID NOT NULL,
            customer_account_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_support_account_grants PRIMARY KEY (user_id, customer_account_id),
            CONSTRAINT fk_support_account_grants_user_id_users FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
            CONSTRAINT fk_support_account_grants_customer_account_id_customer_accounts FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE auth_attempt_windows (
            key_hash TEXT NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            attempts INTEGER NOT NULL,
            CONSTRAINT pk_auth_attempt_windows PRIMARY KEY (key_hash),
            CONSTRAINT ck_auth_attempt_windows_attempts CHECK (attempts > 0)
        )
    """)


def downgrade() -> None:
    for table in (
        "auth_attempt_windows",
        "support_account_grants",
        "auth_invitations",
        "auth_sessions",
        "auth_credentials",
    ):
        op.drop_table(table)
