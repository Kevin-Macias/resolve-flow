"""Persist preliminary support evidence operations and immutable results."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE evidence_analyses (
            id UUID NOT NULL,
            report_id UUID NOT NULL,
            customer_account_id UUID NOT NULL,
            operation_id UUID NOT NULL,
            status TEXT NOT NULL,
            provider_mode TEXT NOT NULL,
            input_hash TEXT NOT NULL,
            input_record JSONB NOT NULL,
            result_record JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_evidence_analyses PRIMARY KEY (id),
            CONSTRAINT uq_evidence_analyses_report_id UNIQUE (report_id, operation_id),
            CONSTRAINT fk_evidence_analyses_report_id_issue_reports
                FOREIGN KEY (report_id) REFERENCES issue_reports(id) ON DELETE RESTRICT,
            CONSTRAINT fk_evidence_analyses_customer_account_id_customer_accounts
                FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id) ON DELETE RESTRICT,
            CONSTRAINT ck_evidence_analyses_status CHECK (status IN ('pending', 'ready', 'failed')),
            CONSTRAINT ck_evidence_analyses_provider_mode CHECK (provider_mode IN ('offline', 'live')),
            CONSTRAINT ck_evidence_analyses_input_hash CHECK (input_hash ~ '^[0-9a-f]{64}$')
        )
    """)
    op.create_index(
        "ix_evidence_analyses_report_id", "evidence_analyses", ["report_id"]
    )


def downgrade() -> None:
    op.drop_table("evidence_analyses")
