"""Persist report-bound customer intake runs and accepted operations.

Revision ID: 0003
Revises: 0002
Frozen SQL independent of future application ORM changes.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = (
    """
CREATE TABLE intake_runs (
    id UUID NOT NULL, 
    report_id UUID NOT NULL, 
    customer_account_id UUID NOT NULL, 
    initiated_by UUID NOT NULL, 
    provider_mode TEXT NOT NULL, 
    revision BIGINT NOT NULL, 
    public_view JSONB NOT NULL, 
    pending_operation_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_intake_runs PRIMARY KEY (id), 
    CONSTRAINT ck_intake_runs_revision CHECK (revision BETWEEN 1 AND 9007199254740991), 
    CONSTRAINT ck_intake_runs_provider_mode CHECK (provider_mode IN ('offline', 'live')), 
    CONSTRAINT uq_intake_runs_report_id UNIQUE (report_id), 
    CONSTRAINT fk_intake_runs_report_id_issue_reports FOREIGN KEY(report_id) REFERENCES issue_reports (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_intake_runs_customer_account_id_customer_accounts FOREIGN KEY(customer_account_id) REFERENCES customer_accounts (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_intake_runs_initiated_by_users FOREIGN KEY(initiated_by) REFERENCES users (id) ON DELETE RESTRICT
)
    """,
    """
CREATE TABLE intake_operations (
    run_id UUID NOT NULL, 
    id UUID NOT NULL, 
    kind TEXT NOT NULL, 
    payload JSONB NOT NULL, 
    payload_hash TEXT NOT NULL, 
    completed BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_intake_operations PRIMARY KEY (run_id, id), 
    CONSTRAINT ck_intake_operations_kind CHECK (kind IN ('start', 'clarification')), 
    CONSTRAINT ck_intake_operations_payload_hash CHECK (payload_hash ~ '^[0-9a-f]{64}$'), 
    CONSTRAINT fk_intake_operations_run_id_intake_runs FOREIGN KEY(run_id) REFERENCES intake_runs (id) ON DELETE RESTRICT
)
    """,
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("intake_operations")
    op.drop_table("intake_runs")
