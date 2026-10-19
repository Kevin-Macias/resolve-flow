"""Durable model-attempt metadata and explicit accounting coverage markers."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE intake_runs ADD COLUMN accounting_version INTEGER")
    op.execute("ALTER TABLE evidence_analyses ADD COLUMN accounting_version INTEGER")
    op.execute("""
        CREATE TABLE model_call_attempts (
            id UUID NOT NULL,
            report_id UUID NOT NULL,
            customer_account_id UUID NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id UUID NOT NULL,
            operation_id UUID NOT NULL,
            call_id UUID NOT NULL,
            attempt INTEGER NOT NULL,
            record JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_model_call_attempts PRIMARY KEY (id),
            CONSTRAINT fk_model_call_attempts_report_id_issue_reports FOREIGN KEY (report_id) REFERENCES issue_reports(id) ON DELETE RESTRICT,
            CONSTRAINT fk_model_call_attempts_customer_account_id_customer_accounts FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id) ON DELETE RESTRICT,
            CONSTRAINT ck_model_call_attempts_scope_type CHECK (scope_type IN ('intake','evidence')),
            CONSTRAINT ck_model_call_attempts_attempt CHECK (attempt >= 1),
            CONSTRAINT uq_model_call_attempts_call_id UNIQUE (call_id, attempt)
        )
    """)
    op.execute(
        "CREATE INDEX ix_model_call_attempts_report_id ON model_call_attempts (report_id)"
    )


def downgrade() -> None:
    op.drop_table("model_call_attempts")
    op.execute("ALTER TABLE evidence_analyses DROP COLUMN accounting_version")
    op.execute("ALTER TABLE intake_runs DROP COLUMN accounting_version")
